"""Structured visual briefs and hard-requirement photo matching.

Stock photographs are scored against a complete scene brief, not isolated
keywords. Metadata (query/title/tags/URL/filename) can REJECT a candidate.
It cannot by itself mark a photo ready for approval. Downloaded pixels are
inspected for technical fitness; if local content validation is not
confident, the photo is NEEDS USER REVIEW.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from PIL import Image

MATCH_PASS = "pass"
MATCH_REJECT = "reject"
MATCH_NEEDS_REVIEW = "needs_user_review"

MIN_PRINT_WIDTH = 800
MIN_PRINT_HEIGHT = 500
MIN_VARIANCE = 12.0
DEFAULT_MIN_SCORE = 0.72

_SOURCE_HOST_RE = re.compile(
    r"(pexels|shutterstock|unsplash|gettyimages|adobestock|istockphoto|depositphotos)",
    re.I,
)
_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)

EVENT_PRINT_QUERIES = (
    "on-site event photo printing station",
    "event photographer printing guest photos",
    "wedding photo booth printer photographs",
    "professional event instant photo printing",
)


PURPOSE_LIVE_CAPTURE = "live_capture"
PURPOSE_EQUIPMENT_KIT = "equipment_kit"
PURPOSE_ONSITE_PRINT = "onsite_print_delivery"
PURPOSE_KEEPSAKE = "keepsake_product"
PURPOSE_FAMILY_REVIEW = "family_review"
PURPOSE_CHAPTER_SCENE = "chapter_scene"

_ISOLATED_SCENE_WORDS = ["photo", "print", "camera", "event"]

PHOTO_LED = "photo_led"
INFORMATION_LED = "information_led"

_PHOTO_LED_HINTS = (
    "garden", "gardening", "vegetable", "herb", "cook", "cooking", "recipe",
    "travel", "craft", "crafts", "fitness", "workout", "yoga", "photograph",
    "photography", "home improvement", "fashion", "animal", "animals", "dog",
    "cat", "bird", "equipment", "woodwork", "paint", "interior design", "plant",
    "balcony", "patio", "food", "kitchen", "bake", "baking", "flower", "pet",
    # Physical instruction / exercise demonstration — a reader of this kind of
    # book reasonably expects to SEE the movement or technique, not just read
    # about it. Kept as general domain terms, not tied to any one topic.
    "kettlebell", "exercise", "strength training", "weightlifting", "weight training",
    "dumbbell", "barbell", "resistance band", "bodyweight", "calisthenics",
    "stretching", "mobility", "warm-up", "warmup", "cardio", "pilates",
    "martial arts", "boxing", "cycling", "running", "swimming", "hiking",
    "dance", "physical therapy", "rehab", "posture", "squat", "deadlift",
    "push-up", "pushup", "form and technique", "repair", "diy", "sewing",
    "knitting", "pottery", "woodworking", "makeup", "skincare", "hairstyle",
    "massage", "first aid",
)
_INFORMATION_LED_HINTS = (
    "budget", "budgeting", "business system", "process", "schedule", "planning",
    "comparison", "online safety", "policy", "strategy", "spreadsheet",
    "workflow", "compliance", "abstract", "accounting",
)
_COVER_VEG = (
    "vegetable", "vegetables", "tomato", "tomatoes", "lettuce", "pepper",
    "peppers", "herb", "herbs", "basil", "kale", "salad", "plant", "plants",
    "greens", "seedling",
)
_COVER_POT = (
    "pot", "pots", "container", "containers", "planter", "planters",
    "bucket", "trough", "raised bed",
)
_COVER_PLACE = (
    "garden", "patio", "balcony", "porch", "terrace", "yard", "backyard",
    "greenhouse", "allotment",
)


@dataclass
class VisualBrief:
    chapter_number: int = 0
    chapter_title: str = ""
    required_subject: str = ""
    required_action: str = ""
    required_setting: str = ""
    required_objects: list[str] = field(default_factory=list)
    forbidden_settings: list[str] = field(default_factory=list)
    business_purpose: str = ""
    min_match_score: float = DEFAULT_MIN_SCORE
    search_queries: list[str] = field(default_factory=list)
    subject_tokens: list[str] = field(default_factory=list)
    action_tokens: list[str] = field(default_factory=list)
    setting_tokens: list[str] = field(default_factory=list)
    object_token_groups: list[list[str]] = field(default_factory=list)
    forbidden_tokens: list[str] = field(default_factory=list)
    generic_tokens: list[str] = field(default_factory=list)
    isolated_keywords: list[str] = field(default_factory=list)
    purpose: str = PURPOSE_CHAPTER_SCENE

    def required_scene(self) -> str:
        objects = ", ".join(self.required_objects)
        return (
            f"Ch {self.chapter_number} {self.chapter_title}: {self.required_subject}; "
            f"{self.required_action}; {self.required_setting}; visible: {objects}."
        )

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["required_scene"] = self.required_scene()
        return payload


@dataclass
class MatchReport:
    status: str
    match_score: float
    passed_requirements: list[str] = field(default_factory=list)
    missing_requirements: list[str] = field(default_factory=list)
    rejection_reason: str = ""
    appears_to_show: str = ""
    required_scene: str = ""
    technical_ok: bool = False
    content_verified: bool = False
    user_accepted: bool = False
    seen_full_size: bool = False
    replacement_queries: list[str] = field(default_factory=list)
    brief: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == MATCH_PASS

    def as_dict(self) -> dict[str, Any]:
        return {
            "match_status": self.status,
            "match_score": round(float(self.match_score), 3),
            "passed_requirements": list(self.passed_requirements),
            "missing_requirements": list(self.missing_requirements),
            "rejection_reason": self.rejection_reason,
            "appears_to_show": self.appears_to_show,
            "required_scene": self.required_scene,
            "technical_ok": self.technical_ok,
            "content_verified": self.content_verified,
            "user_accepted": self.user_accepted,
            "seen_full_size": self.seen_full_size,
            "replacement_queries": list(self.replacement_queries),
            "visual_brief": self.brief,
        }


def _norm(text: Any) -> str:
    raw = unquote(str(text or "").replace("-", " ").replace("_", " ").replace("/", " "))
    raw = re.sub(r"[^a-z0-9\s]+", " ", raw.lower())
    return re.sub(r"\s+", " ", raw).strip()


def _blob(*parts: Any) -> str:
    return _norm(" ".join(str(p or "") for p in parts if str(p or "").strip()))


def _has_any(text: str, tokens: list[str]) -> bool:
    return any(tok and tok in text for tok in tokens)


def _slug_from_url(url: str) -> str:
    path = urlparse(str(url or "")).path
    if not path:
        return ""
    name = path.rstrip("/").split("/")[-1]
    name = re.sub(r"-\d+$", "", name)
    return _norm(name)


def photo_appearance_text(
    *,
    alt: str = "",
    page_url: str = "",
    filename: str = "",
    tags: Any = None,
    content_labels: Any = None,
    photographer: str = "",
) -> str:
    """What the selected photo appears to show. Never uses the planned caption."""
    tag_text = ""
    if isinstance(tags, (list, tuple)):
        tag_text = " ".join(str(t) for t in tags)
    elif isinstance(tags, str):
        tag_text = tags
    label_text = ""
    if isinstance(content_labels, (list, tuple)):
        label_text = " ".join(str(t) for t in content_labels)
    elif isinstance(content_labels, str):
        label_text = content_labels
    return _blob(alt, _slug_from_url(page_url), Path(str(filename or "")).stem, tag_text, label_text, photographer)


def event_print_brief(*, chapter_number: int = 7, chapter_title: str = "") -> VisualBrief:
    title = chapter_title or "Event-Day Operations: From Photograph to Guest Delivery"
    return VisualBrief(
        chapter_number=chapter_number,
        chapter_title=title,
        required_subject="event photographer, assistant, or station operator",
        required_action="producing or handing off guest photo prints",
        required_setting="event venue, reception, booth, or on-site workstation",
        required_objects=[
            "compact photo printer",
            "bordered photographs",
            "camera or computer when visible",
        ],
        forbidden_settings=[
            "home office",
            "craft table",
            "ordinary document printer",
            "generic person using a printer",
            "printer with no photographs",
            "photo editing without print delivery",
        ],
        business_purpose="Show the capture-to-print-to-guest-delivery station this chapter teaches.",
        min_match_score=DEFAULT_MIN_SCORE,
        search_queries=list(EVENT_PRINT_QUERIES),
        subject_tokens=[
            "event photographer",
            "photographer",
            "assistant",
            "operator",
            "booth attendant",
            "staff",
        ],
        action_tokens=[
            "printing guest",
            "handing",
            "hand off",
            "deliver",
            "producing prints",
            "prints emerging",
            "photo coming out",
            "guest photos",
            "instant print",
        ],
        setting_tokens=[
            "event",
            "wedding",
            "reception",
            "booth",
            "venue",
            "on site",
            "onsite",
            "workstation",
            "guest station",
        ],
        object_token_groups=[
            ["photo printer", "dye sub", "dye-sub", "instant printer", "compact printer", "event printer"],
            ["bordered photograph", "bordered photo", "photo print", "photographs", "prints emerging", "instant photo"],
        ],
        forbidden_tokens=[
            "home office",
            "at home",
            "working at home",
            "forking at home",
            "apartment",
            "craft",
            "scrapbook",
            "3d print",
            "3-d print",
            "receipt printer",
            "label printer",
            "document printer",
            "office worker",
            "workplace",
            "toner",
            "cartridge",
            "ink cartridge",
            "hair salon",
            "barber",
            "editing photographs on computer",
            "editing photos on computer",
            "man editing photographs",
        ],
        generic_tokens=[
            "woman printing",
            "person using printer",
            "using printer",
            "woman working on laptop and printing",
            "serious female office worker using printer",
        ],
        isolated_keywords=["printer", "print", "photo", "photograph", "camera", "event"],
        purpose=PURPOSE_ONSITE_PRINT,
    )


def _fresh_strings(values: Any) -> list[str]:
    return [str(item) for item in list(values or []) if str(item).strip()]


def _fresh_groups(values: Any) -> list[list[str]]:
    groups: list[list[str]] = []
    for group in list(values or []):
        if isinstance(group, (list, tuple)):
            copied = [str(item) for item in group if str(item).strip()]
            if copied:
                groups.append(copied)
        elif str(group).strip():
            groups.append([str(group)])
    return groups


def _visual_only_text(aid: dict[str, Any] | None) -> str:
    row = aid if isinstance(aid, dict) else {}
    return _blob(
        row.get("title"),
        row.get("caption"),
        row.get("business_purpose"),
        row.get("asset_description"),
        row.get("planned_description"),
    )


def _has_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase and phrase in text for phrase in phrases)


def _is_print_contrast(text: str) -> bool:
    return _has_any_phrase(
        text,
        (
            "beyond photo prints",
            "beyond prints",
            "keepsakes beyond",
            "separate from",
            "separate equipment",
            "different workflow",
            "not just another",
            "not another version",
        ),
    )


def _has_keepsake_product(text: str) -> bool:
    return _has_any_phrase(
        text,
        (
            "mug",
            "ceramic",
            "plate",
            "shirt",
            "t shirt",
            "metal print",
            "photo on stone",
            "stone print",
            "photo on glass",
            "glass print",
            "button",
            "keepsake",
            "tumbler",
            "tote",
            "ornament",
            "photo applied",
            "photograph applied",
            "image applied",
        ),
    )


def _has_equipment_kit(text: str) -> bool:
    return _has_any_phrase(
        text,
        (
            "camera kit",
            "core camera kit",
            "backup gear",
            "camera body",
            "support gear",
            "photography equipment",
            "camera equipment",
            "event photography kit",
            "gear staged",
            "kit laid",
            "laid out",
            "staged as",
            "equipment on a table",
            "lenses and support",
            "lenses, support",
        ),
    )


def _has_onsite_print_station(text: str) -> bool:
    return _has_any_phrase(
        text,
        (
            "photo printer",
            "on site print",
            "onsite print",
            "guest delivery",
            "capture to print",
            "print to guest",
            "guest photo print",
            "bordered photograph",
            "bordered photographs",
            "prints emerging",
            "instant print station",
            "photo booth printer",
            "on site workstation",
            "onsite workstation",
            "printing guest photos",
            "guest pickup",
        ),
    )


def _has_live_capture(text: str) -> bool:
    has_photographer = "photographer" in text
    has_action = _has_any_phrase(
        text,
        ("photographing", "covering", "shooting", "captures", "capturing", "actively photograph"),
    )
    has_live = _has_any_phrase(
        text,
        (
            "live event",
            "live celebration",
            "wedding",
            "reception",
            "celebration",
            "covering a live",
            "working photographer",
        ),
    )
    return bool(has_photographer and (has_action or has_live))


def derive_visual_purpose(
    aid: dict[str, Any] | None = None,
    *,
    chapter: str = "",
    chapter_body: str = "",
) -> str:
    """Classify THIS visual from its own planned scene. Never inherit a prior chapter."""
    row = aid if isinstance(aid, dict) else {}
    visual = _visual_only_text(row)
    chapter_text = _blob(chapter or row.get("chapter"), chapter_body or row.get("chapter_body") or row.get("manuscript_excerpt"))
    combined = visual or chapter_text
    if "parent" in combined and "teen" in combined:
        return PURPOSE_FAMILY_REVIEW
    if _has_keepsake_product(visual):
        return PURPOSE_KEEPSAKE
    if _has_equipment_kit(visual):
        return PURPOSE_EQUIPMENT_KIT
    if _has_onsite_print_station(visual):
        return PURPOSE_ONSITE_PRINT
    if _has_live_capture(visual):
        return PURPOSE_LIVE_CAPTURE
    if _has_keepsake_product(chapter_text) and not _has_onsite_print_station(visual):
        return PURPOSE_KEEPSAKE
    if _has_equipment_kit(chapter_text) and not _has_onsite_print_station(visual):
        return PURPOSE_EQUIPMENT_KIT
    if _has_onsite_print_station(chapter_text) and not _is_print_contrast(chapter_text):
        return PURPOSE_ONSITE_PRINT
    if _has_live_capture(chapter_text):
        return PURPOSE_LIVE_CAPTURE
    return PURPOSE_CHAPTER_SCENE


def _purpose_from_stored_brief(existing: dict[str, Any]) -> str:
    stored = str(existing.get("purpose") or "").strip()
    if stored in {
        PURPOSE_LIVE_CAPTURE,
        PURPOSE_EQUIPMENT_KIT,
        PURPOSE_ONSITE_PRINT,
        PURPOSE_KEEPSAKE,
        PURPOSE_FAMILY_REVIEW,
        PURPOSE_CHAPTER_SCENE,
    }:
        return stored
    blob = _blob(
        existing.get("required_subject"),
        existing.get("required_action"),
        existing.get("required_setting"),
        " ".join(_fresh_strings(existing.get("required_objects"))),
        existing.get("business_purpose"),
    )
    if _has_keepsake_product(blob):
        return PURPOSE_KEEPSAKE
    if _has_onsite_print_station(blob) or "guest photo print" in blob or "compact photo printer" in blob:
        return PURPOSE_ONSITE_PRINT
    if _has_equipment_kit(blob) or "working kit" in blob:
        return PURPOSE_EQUIPMENT_KIT
    if "working event photographer" in blob or "photographing a live" in blob:
        return PURPOSE_LIVE_CAPTURE
    return PURPOSE_CHAPTER_SCENE


def classify_ebook_subject(*, title: str = "", topic: str = "", content: str = "") -> str:
    """Photo-led topics need real photographs; information-led topics may use charts."""
    blob = _norm(f"{title} {topic} {str(content or '')[:800]}")
    photo_hit = any(token in blob for token in _PHOTO_LED_HINTS)
    info_hit = any(token in blob for token in _INFORMATION_LED_HINTS)
    if photo_hit and not info_hit:
        return PHOTO_LED
    if info_hit and not photo_hit:
        return INFORMATION_LED
    if photo_hit:
        return PHOTO_LED
    return INFORMATION_LED


def is_photo_led_subject(*, title: str = "", topic: str = "", content: str = "") -> bool:
    return classify_ebook_subject(title=title, topic=topic, content=content) == PHOTO_LED


_GARDEN_REJECT_TOKENS = (
    "pasta", "recipe", "kitchen", "bathroom", "lotion", "serum", "conditioner",
    "cosmetic", "skincare", "maraschino", "after sun", "hair dryer", "shampoo",
)
_GARDEN_NEED_TOKENS = (
    "pot", "pots", "planter", "container", "garden", "soil", "plant", "plants",
    "seedling", "balcony", "patio", "watering", "harvest", "leaf", "leaves",
    "tomato", "herb", "vegetable", "seed",
)


def garden_photo_usable(photo: dict[str, Any] | None, *, image_bytes: bytes | None = None) -> bool:
    del image_bytes
    row = photo if isinstance(photo, dict) else {}
    appearance = _blob(row.get("alt"), row.get("page_url"), row.get("photographer"), row.get("filename"))
    if _has_any(appearance, list(_GARDEN_REJECT_TOKENS)):
        return False
    return _has_any(appearance, list(_GARDEN_NEED_TOKENS))


def score_cover_photo(photo: dict[str, Any] | None, *, title: str = "", topic: str = "") -> float:
    """Rank a Pexels cover candidate. Metadata can reject; it cannot invent a pass."""
    from services.ebook_visual_brief_common import detect_equipment_terms, excluded_equipment_terms

    row = photo if isinstance(photo, dict) else {}
    appearance = _blob(row.get("alt"), row.get("page_url"), row.get("photographer"), row.get("photo_id"))
    garden = any(
        token in _norm(f"{title} {topic}")
        for token in ("garden", "vegetable", "herb", "plant", "patio", "balcony")
    )
    equipment = detect_equipment_terms(title, topic)
    if equipment:
        # A cover photo of the wrong named implement is wrong regardless of
        # resolution/orientation -- hard reject, don't just down-rank it.
        wrong = [t for t in excluded_equipment_terms(equipment) if t in appearance]
        if wrong and not any(t in appearance for t in equipment):
            return 0.0
    if not garden:
        width = int(row.get("width") or 0)
        height = int(row.get("height") or 0)
        if width < MIN_PRINT_WIDTH or height < MIN_PRINT_HEIGHT:
            return 0.0
        score = 0.4
        if height >= width:
            score += 0.2
        if appearance:
            score += 0.1
        if equipment and any(t in appearance for t in equipment):
            score += 0.2
        return score
    veg = _has_any(appearance, list(_COVER_VEG))
    pot = _has_any(appearance, list(_COVER_POT))
    place = _has_any(appearance, list(_COVER_PLACE))
    if not (veg or pot or place):
        return 0.0
    score = 0.15
    if veg:
        score += 0.4
    if pot:
        score += 0.25
    if place:
        score += 0.2
    if int(row.get("height") or 0) >= int(row.get("width") or 0):
        score += 0.1
    return round(score, 3)


def gardening_chapter_brief(aid: dict[str, Any], *, chapter: str = "") -> VisualBrief:
    chapter_title = str(chapter or aid.get("chapter") or "")
    caption = str(aid.get("caption") or aid.get("title") or chapter_title)
    low = _norm(f"{chapter_title} {caption}")
    if "soil" in low or ("container" in low and "choos" in low):
        queries = ["garden pots and potting soil", "potting mix vegetable container", "drainage holes garden pots"]
    elif "vegetable" in low or "herb" in low or "crop" in low or "picking" in low:
        queries = ["tomatoes peppers lettuce herbs containers", "potted tomatoes and herbs"]
    elif "water" in low or "sun" in low or "care" in low:
        queries = ["watering patio vegetables", "watering potted tomatoes"]
    elif "pest" in low or "problem" in low:
        queries = ["garden pests damaged vegetable leaves", "aphids on potted plants"]
    elif "harvest" in low or "replant" in low:
        queries = ["harvesting tomatoes herbs from pots", "picking basil from patio pot"]
    else:
        queries = ["beginner container garden", "balcony vegetable pots", "container garden tomatoes lettuce herbs"]
    return _new_brief(
        chapter_number=int(aid.get("chapter_index") or 0),
        chapter_title=chapter_title,
        required_subject="vegetables, herbs, or container plants",
        required_action="growing, planting, watering, or harvesting in containers",
        required_setting="garden, patio, balcony, or pots",
        required_objects=["pot, container, plant, vegetable, or herb"],
        forbidden_settings=["office", "abstract background", "clip art"],
        business_purpose=caption or "Show the real container-garden scene this chapter teaches.",
        search_queries=queries,
        subject_tokens=["vegetable", "herb", "tomato", "lettuce", "plant", "garden", "pot", "container"],
        action_tokens=["growing", "planting", "watering", "harvest", "potted", "container", "pot", "soil"],
        setting_tokens=["garden", "patio", "balcony", "pot", "container", "outdoor", "yard", "porch"],
        object_token_groups=[["pot", "pots", "container", "planter", "plant", "vegetable", "herb", "tomato", "soil"]],
        forbidden_tokens=["clip art", "watermark", "advertisement", "kitchen", "pasta", "recipe", "bathroom", "lotion", "cosmetic", "skincare"],
        generic_tokens=[],
        isolated_keywords=[],
        purpose=PURPOSE_CHAPTER_SCENE,
        min_match_score=0.45,
    )


def _default_search_queries(brief: VisualBrief) -> list[str]:
    if brief.purpose == PURPOSE_ONSITE_PRINT:
        return list(EVENT_PRINT_QUERIES)
    query = " ".join(
        part
        for part in (brief.required_subject, brief.required_action, brief.required_setting)
        if part and "named in the requested" not in part
    ).strip()
    return [query] if query else _fresh_strings([brief.chapter_title or "photograph"])


def _new_brief(
    *,
    chapter_number: int,
    chapter_title: str,
    required_subject: str,
    required_action: str,
    required_setting: str,
    required_objects: list[str],
    forbidden_settings: list[str],
    business_purpose: str,
    search_queries: list[str],
    subject_tokens: list[str],
    action_tokens: list[str],
    setting_tokens: list[str],
    object_token_groups: list[list[str]],
    forbidden_tokens: list[str],
    generic_tokens: list[str],
    isolated_keywords: list[str],
    purpose: str,
    min_match_score: float = DEFAULT_MIN_SCORE,
) -> VisualBrief:
    return VisualBrief(
        chapter_number=int(chapter_number or 0),
        chapter_title=str(chapter_title or ""),
        required_subject=str(required_subject or ""),
        required_action=str(required_action or ""),
        required_setting=str(required_setting or ""),
        required_objects=_fresh_strings(required_objects),
        forbidden_settings=_fresh_strings(forbidden_settings),
        business_purpose=str(business_purpose or ""),
        min_match_score=float(min_match_score or DEFAULT_MIN_SCORE),
        search_queries=_fresh_strings(search_queries),
        subject_tokens=_fresh_strings(subject_tokens),
        action_tokens=_fresh_strings(action_tokens),
        setting_tokens=_fresh_strings(setting_tokens),
        object_token_groups=_fresh_groups(object_token_groups),
        forbidden_tokens=_fresh_strings(forbidden_tokens),
        generic_tokens=_fresh_strings(generic_tokens),
        isolated_keywords=_fresh_strings(isolated_keywords or _ISOLATED_SCENE_WORDS),
        purpose=str(purpose or PURPOSE_CHAPTER_SCENE),
    )


def live_capture_brief(*, chapter_number: int = 0, chapter_title: str = "", business_purpose: str = "") -> VisualBrief:
    return _new_brief(
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        required_subject="photographer",
        required_action="actively photographing",
        required_setting="live wedding, reception, event, or celebration",
        required_objects=["visible camera"],
        forbidden_settings=[],
        business_purpose=business_purpose or "Show a photographer working a live event or celebration.",
        search_queries=[
            "photographer photographing live wedding reception",
            "event photographer covering a celebration with camera",
        ],
        subject_tokens=["photographer"],
        action_tokens=["photographing", "covering", "shooting", "captures", "capturing", "camera"],
        setting_tokens=["wedding", "reception", "celebration", "live event", "event"],
        object_token_groups=[["camera", "camera body"]],
        forbidden_tokens=[],
        generic_tokens=[],
        isolated_keywords=list(_ISOLATED_SCENE_WORDS),
        purpose=PURPOSE_LIVE_CAPTURE,
    )


def equipment_kit_brief(*, chapter_number: int = 0, chapter_title: str = "", business_purpose: str = "") -> VisualBrief:
    return _new_brief(
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        required_subject="professional camera equipment or event-photography kit",
        required_action="equipment arranged as a working kit",
        required_setting="table, studio, or kit layout showing gear",
        required_objects=["visible camera body", "lenses, support, storage, lighting, or backup gear"],
        forbidden_settings=[],
        business_purpose=business_purpose or "Show the working camera kit this chapter teaches, not a live event.",
        search_queries=[
            "professional camera body lenses and support gear on a table",
            "photography equipment kit laid out camera body",
        ],
        subject_tokens=[
            "camera kit",
            "camera equipment",
            "photography equipment",
            "camera body",
            "camera",
            "gear",
        ],
        action_tokens=["laid out", "staged", "arranged", "on a table", "kit", "equipment"],
        setting_tokens=["table", "studio", "kit", "gear", "equipment"],
        object_token_groups=[
            ["camera body", "camera"],
            ["lens", "lenses", "support", "tripod", "storage", "lighting", "flash", "backup", "photography equipment", "equipment"],
        ],
        forbidden_tokens=[],
        generic_tokens=[],
        isolated_keywords=list(_ISOLATED_SCENE_WORDS),
        purpose=PURPOSE_EQUIPMENT_KIT,
    )


def keepsake_product_brief(*, chapter_number: int = 0, chapter_title: str = "", business_purpose: str = "") -> VisualBrief:
    return _new_brief(
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        required_subject="finished photographic keepsake",
        required_action="photographic image visibly applied to the product",
        required_setting="product scene separate from an ordinary photo print",
        required_objects=["mug, plate, shirt, metal print, stone, glass, button, or similar"],
        forbidden_settings=[],
        business_purpose=business_purpose or "Show a finished photographic product, not an ordinary photo print.",
        search_queries=[
            "ceramic mug with photograph printed on it",
            "photo keepsake mug plate shirt metal print",
        ],
        subject_tokens=["keepsake", "mug", "ceramic", "plate", "shirt", "metal print", "product"],
        action_tokens=["applied", "printed on", "photograph on", "photo on", "image on", "photograph applied"],
        setting_tokens=["mug", "plate", "shirt", "product", "surface", "keepsake", "ceramic"],
        object_token_groups=[
            ["mug", "ceramic", "plate", "shirt", "metal print", "stone", "glass", "button", "keepsake", "tumbler"],
        ],
        forbidden_tokens=[],
        generic_tokens=[],
        isolated_keywords=list(_ISOLATED_SCENE_WORDS),
        purpose=PURPOSE_KEEPSAKE,
    )


_SCENE_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "this", "that",
    "from", "your", "you", "chapter", "stock", "photo", "photograph", "image", "visual",
    "show", "showing", "shown", "named", "requested", "scene", "planned", "ebook",
}


def _significant_tokens(text: str, *, limit: int = 8) -> list[str]:
    out: list[str] = []
    for word in _norm(text).split():
        if len(word) < 4 or word in _SCENE_STOPWORDS:
            continue
        if word not in out:
            out.append(word)
        if len(out) >= limit:
            break
    return out


def _chapter_scene_brief_from_text(
    aid: dict[str, Any],
    *,
    chapter: str = "",
    chapter_body: str = "",
    book_title: str = "",
    book_topic: str = "",
) -> VisualBrief:
    """Independent structured brief for an arbitrary chapter photograph."""
    from services.ebook_visual_brief_common import (
        detect_audience_terms,
        detect_equipment_terms,
        excluded_equipment_terms,
        strip_filler,
    )

    title = str(aid.get("title") or "")
    caption = str(aid.get("caption") or aid.get("description") or "")
    chapter_title = str(chapter or aid.get("chapter") or "")
    chapter_number = int(aid.get("chapter_index") or 0)
    planned = caption or title or chapter_title or "the subject of this chapter"
    body = str(chapter_body or aid.get("chapter_body") or aid.get("manuscript_excerpt") or "")
    purpose_text = caption or title or f"Help the reader understand {chapter_title or 'this chapter'}."

    # Strip non-visual connective phrases ("without guessing", "turning
    # power into", ...) before tokenizing, so the fixed-size token budget
    # below is spent on words that actually describe something a
    # photograph could show, not table-of-contents phrasing.
    clean_title = strip_filler(title)
    clean_caption = strip_filler(caption)
    clean_chapter_title = strip_filler(chapter_title)

    blob = " ".join(part for part in (clean_title, clean_caption, clean_chapter_title, body[:400]) if str(part).strip())
    tokens = _significant_tokens(blob, limit=10)
    subject_tokens = _significant_tokens(clean_title or clean_chapter_title or planned, limit=5) or tokens[:4]
    action_tokens = _significant_tokens(clean_caption or planned, limit=5) or tokens[1:5]
    setting_tokens = _significant_tokens(clean_chapter_title or body[:180], limit=5) or tokens[:4]
    object_tokens = tokens[:5]

    # The book's own defining equipment/implement (if any) is detected from
    # the BOOK title/topic -- not just this one chapter's title -- so it
    # survives every chapter query even when a chapter title never restates
    # it (e.g. "The Deadlift: Learning to Hinge Without Guessing" never says
    # "kettlebell", but the book is a kettlebell book).
    equipment = detect_equipment_terms(book_title, book_topic, chapter_title)
    audience = detect_audience_terms(book_title, book_topic)
    if equipment:
        for term in reversed(equipment):
            if term not in subject_tokens:
                subject_tokens.insert(0, term)
            if term not in object_tokens:
                object_tokens.insert(0, term)
    if audience:
        for term in audience:
            if term not in subject_tokens:
                subject_tokens.append(term)

    queries: list[str] = []
    equipment_prefix = " ".join(equipment[:1])
    for item in (
        f"{equipment_prefix} {clean_chapter_title}".strip() if equipment_prefix else "",
        f"{equipment_prefix} {' '.join(action_tokens[:3])}".strip() if equipment_prefix else "",
        planned,
        clean_title,
        clean_caption,
        " ".join(subject_tokens[:4]),
        " ".join(f"{clean_chapter_title} {' '.join(object_tokens[:3])}".split()),
        " ".join(tokens[:6]),
    ):
        text = " ".join(str(item or "").split())
        if text and text not in queries and "named in the requested" not in text.lower():
            queries.append(text[:120])
    if not queries:
        queries = [chapter_title or "educational photograph"]

    forbidden_tokens = ["watermark", "advertisement"]
    if equipment:
        # A photo of the wrong implement is definitionally wrong no matter
        # how well its metadata otherwise matches this chapter's words.
        forbidden_tokens.extend(excluded_equipment_terms(equipment))

    return _new_brief(
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        required_subject=(f"{equipment_prefix} " if equipment_prefix else "") + (title or chapter_title or "the people or subject this chapter teaches"),
        required_action=caption or "the action this chapter teaches",
        required_setting=chapter_title or "the setting described in this chapter",
        required_objects=object_tokens[:5] or ["the objects named in this chapter"],
        forbidden_settings=["watermark", "advertisement", "stock photo collage"],
        business_purpose=purpose_text,
        search_queries=queries[:6],
        subject_tokens=subject_tokens,
        action_tokens=action_tokens,
        setting_tokens=setting_tokens,
        object_token_groups=([equipment] if equipment else []) + ([object_tokens[:4]] if object_tokens else []),
        forbidden_tokens=forbidden_tokens,
        generic_tokens=[],
        isolated_keywords=list(_ISOLATED_SCENE_WORDS),
        purpose=PURPOSE_CHAPTER_SCENE,
    )


def _generic_photo_brief(
    aid: dict[str, Any],
    *,
    chapter: str = "",
    chapter_body: str = "",
    book_title: str = "",
    book_topic: str = "",
) -> VisualBrief:
    title = str(aid.get("title") or "")
    caption = str(aid.get("caption") or "")
    chapter_title = str(chapter or aid.get("chapter") or "")
    chapter_number = int(aid.get("chapter_index") or 0)
    purpose = derive_visual_purpose(aid, chapter=chapter_title, chapter_body=chapter_body)
    purpose_text = caption or title or "Illustrate the planned visual for this chapter."
    if purpose == PURPOSE_FAMILY_REVIEW:
        return _new_brief(
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            required_subject="parent and teenager",
            required_action="reviewing a phone or computer together",
            required_setting="family or home setting",
            required_objects=["smartphone or computer"],
            forbidden_settings=[],
            business_purpose=purpose_text,
            search_queries=[
                "parent and teenager reviewing a phone together",
                "parent teenager smartphone at home",
                "family looking at a smartphone together",
            ],
            subject_tokens=["parent", "teen", "teenager", "family"],
            action_tokens=["review", "looking at", "phone", "smartphone", "tablet"],
            setting_tokens=["home", "family", "living room", "together"],
            object_token_groups=[["smartphone", "phone", "computer", "tablet"]],
            forbidden_tokens=[],
            generic_tokens=[],
            isolated_keywords=list(_ISOLATED_SCENE_WORDS),
            purpose=PURPOSE_FAMILY_REVIEW,
        )
    if purpose == PURPOSE_KEEPSAKE:
        return keepsake_product_brief(
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            business_purpose=purpose_text,
        )
    if purpose == PURPOSE_EQUIPMENT_KIT:
        return equipment_kit_brief(
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            business_purpose=purpose_text,
        )
    if purpose == PURPOSE_ONSITE_PRINT:
        brief = event_print_brief(chapter_number=chapter_number, chapter_title=chapter_title)
        if purpose_text:
            brief.business_purpose = purpose_text
        return brief
    if purpose == PURPOSE_LIVE_CAPTURE:
        return live_capture_brief(
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            business_purpose=purpose_text,
        )
    garden_blob = _norm(f"{chapter_title} {title} {caption}")
    if any(
        tok in garden_blob
        for tok in (
            "garden", "vegetable", "herb", "tomato", "potting", "patio", "balcony",
            "container", "soil", "pest", "harvest", "water", "sun", "pot",
        )
    ):
        return gardening_chapter_brief(aid, chapter=chapter_title)
    return _chapter_scene_brief_from_text(
        aid, chapter=chapter_title, chapter_body=chapter_body, book_title=book_title, book_topic=book_topic
    )


def is_event_print_scene(aid: dict[str, Any] | None, *, chapter: str = "") -> bool:
    return derive_visual_purpose(aid, chapter=chapter) == PURPOSE_ONSITE_PRINT


def _brief_from_stored(existing: dict[str, Any], *, chapter_number: int, chapter_title: str) -> VisualBrief:
    purpose = _purpose_from_stored_brief(existing)
    brief = _new_brief(
        chapter_number=int(existing.get("chapter_number") or chapter_number),
        chapter_title=str(existing.get("chapter_title") or chapter_title),
        required_subject=str(existing.get("required_subject") or ""),
        required_action=str(existing.get("required_action") or ""),
        required_setting=str(existing.get("required_setting") or ""),
        required_objects=_fresh_strings(existing.get("required_objects")),
        forbidden_settings=_fresh_strings(existing.get("forbidden_settings")),
        business_purpose=str(existing.get("business_purpose") or ""),
        min_match_score=float(existing.get("min_match_score") or DEFAULT_MIN_SCORE),
        search_queries=_fresh_strings(existing.get("search_queries")),
        subject_tokens=_fresh_strings(existing.get("subject_tokens")),
        action_tokens=_fresh_strings(existing.get("action_tokens")),
        setting_tokens=_fresh_strings(existing.get("setting_tokens")),
        object_token_groups=_fresh_groups(existing.get("object_token_groups")),
        forbidden_tokens=_fresh_strings(existing.get("forbidden_tokens")),
        generic_tokens=_fresh_strings(existing.get("generic_tokens")),
        isolated_keywords=_fresh_strings(existing.get("isolated_keywords") or _ISOLATED_SCENE_WORDS),
        purpose=purpose,
    )
    if not brief.search_queries:
        brief.search_queries = _default_search_queries(brief)
    return brief


def _stored_brief_matches_purpose(existing: dict[str, Any], derived: VisualBrief) -> bool:
    if not existing.get("required_subject"):
        return False
    stored_purpose = _purpose_from_stored_brief(existing)
    if stored_purpose != derived.purpose:
        return False
    stored_blob = _blob(
        existing.get("required_subject"),
        existing.get("required_action"),
        existing.get("required_setting"),
        " ".join(_fresh_strings(existing.get("required_objects"))),
    )
    if derived.purpose == PURPOSE_EQUIPMENT_KIT and ("photographer" in stored_blob and "kit" not in stored_blob):
        return False
    if derived.purpose == PURPOSE_KEEPSAKE and _has_onsite_print_station(stored_blob):
        return False
    if derived.purpose != PURPOSE_ONSITE_PRINT and _has_onsite_print_station(stored_blob) and not _has_keepsake_product(stored_blob):
        return False
    if derived.purpose != PURPOSE_LIVE_CAPTURE and "working event photographer" in stored_blob:
        return False
    return True


def build_visual_brief(
    aid: dict[str, Any] | None = None,
    *,
    chapter: str = "",
    title: str = "",
    topic: str = "",
    chapter_body: str = "",
) -> VisualBrief:
    aid = aid if isinstance(aid, dict) else {}
    existing = aid.get("visual_brief") if isinstance(aid.get("visual_brief"), dict) else None
    chapter_title = str(chapter or aid.get("chapter") or "")
    chapter_number = int(aid.get("chapter_index") or 0)
    derived = _generic_photo_brief(
        aid, chapter=chapter_title, chapter_body=chapter_body, book_title=title, book_topic=topic
    )
    if existing and _stored_brief_matches_purpose(existing, derived):
        stored = _brief_from_stored(existing, chapter_number=chapter_number, chapter_title=chapter_title)
        stored.chapter_number = stored.chapter_number or chapter_number
        stored.chapter_title = stored.chapter_title or chapter_title
        return stored
    return derived


def inspect_local_image(path: str | None, *, image_bytes: bytes | None = None) -> dict[str, Any]:
    findings: list[str] = []
    payload = image_bytes
    if not payload and path and os.path.isfile(path):
        try:
            payload = Path(path).read_bytes()
        except OSError:
            payload = b""
    if not payload:
        return {
            "ok": False,
            "width": 0,
            "height": 0,
            "variance": 0.0,
            "sha256": "",
            "findings": ["missing or unreadable asset"],
            "placeholder": True,
        }
    sha = hashlib.sha256(payload).hexdigest()
    try:
        img = Image.open(io.BytesIO(payload))
        img.load()
        img = img.convert("RGB")
    except Exception:
        return {
            "ok": False,
            "width": 0,
            "height": 0,
            "variance": 0.0,
            "sha256": sha,
            "findings": ["missing or unreadable asset"],
            "placeholder": True,
        }
    width, height = img.size
    if width < MIN_PRINT_WIDTH or height < MIN_PRINT_HEIGHT:
        findings.append("insufficient print resolution")
    gray = img.convert("L").resize((64, 64))
    hist = gray.histogram()
    total = float(sum(hist) or 1)
    mean = sum(i * count for i, count in enumerate(hist)) / total
    variance = (sum(((i - mean) ** 2) * count for i, count in enumerate(hist)) / total) ** 0.5
    placeholder = variance < MIN_VARIANCE
    if placeholder:
        findings.append("image does not look like a photograph")
    watermark = _watermark_hint(img)
    if watermark:
        findings.append("unwanted watermark")
    return {
        "ok": not findings,
        "width": width,
        "height": height,
        "variance": round(variance, 2),
        "sha256": sha,
        "findings": findings,
        "placeholder": placeholder,
        "watermark": watermark,
    }


def _watermark_hint(img: Image.Image) -> bool:
    w, h = img.size
    if w < 80 or h < 80:
        return False
    boxes = [
        img.crop((0, 0, max(40, w // 8), max(24, h // 12))),
        img.crop((w - max(40, w // 8), 0, w, max(24, h // 12))),
        img.crop((0, h - max(24, h // 12), max(40, w // 8), h)),
        img.crop((w - max(40, w // 8), h - max(24, h // 12), w, h)),
    ]
    for box in boxes:
        gray = box.convert("L")
        hist = gray.histogram()
        if not hist:
            continue
        total = sum(hist) or 1
        bright = sum(hist[200:]) / total
        dark = sum(hist[:40]) / total
        if bright > 0.62 and dark > 0.18:
            return True
    return False


def _requirement_hit(text: str, tokens: list[str]) -> bool:
    return _has_any(text, [_norm(tok) for tok in tokens if tok])


def _forbidden_hit(text: str, tokens: list[str]) -> str:
    for tok in tokens:
        needle = _norm(tok)
        if needle and needle in text:
            return tok
    return ""


def _isolated_keyword_only(text: str, keyword: str, context_groups: list[list[str]]) -> bool:
    if keyword not in text:
        return False
    for group in context_groups:
        if _requirement_hit(text, group):
            return False
    return True


def _named_scene_contradiction(planned: str, appearance: str, forbidden: str) -> str:
    """Return a specific contradictory claim, or empty when none can be named."""
    home = _has_any_phrase(
        appearance,
        ("at home", "home office", "working at home", "forking at home", "apartment"),
    )
    onsite_claim = _has_any_phrase(
        planned,
        ("event", "guest", "booth", "reception", "workstation", "on site", "onsite", "venue", "celebration"),
    )
    if home and onsite_claim:
        return (
            "contradictory claim: description requires an on-site event/guest-delivery scene "
            "but the selected photo shows an at-home setting"
        )
    if forbidden and onsite_claim:
        return f"contradictory claim: required on-site scene conflicts with {forbidden}"
    return ""


def score_photo_against_brief(
    brief: VisualBrief,
    *,
    appears_to_show: str = "",
    alt: str = "",
    page_url: str = "",
    filename: str = "",
    tags: Any = None,
    content_labels: Any = None,
    image_path: str | None = None,
    image_bytes: bytes | None = None,
    planned_caption: str = "",
    user_accepted: bool = False,
    seen_full_size: bool = False,
    other_shas: list[str] | None = None,
) -> MatchReport:
    appearance = appears_to_show or photo_appearance_text(
        alt=alt,
        page_url=page_url,
        filename=filename,
        tags=tags,
        content_labels=content_labels,
    )
    inspection = inspect_local_image(image_path, image_bytes=image_bytes) if (image_path or image_bytes) else {
        "ok": False,
        "findings": ["missing or unreadable asset"],
        "sha256": "",
        "placeholder": True,
        "watermark": False,
    }
    passed: list[str] = []
    missing: list[str] = []
    reasons: list[str] = []
    inspected_labels = content_labels not in (None, "", [], ())

    forbidden = _forbidden_hit(appearance, brief.forbidden_tokens)
    if forbidden:
        reasons.append(f"setting conflict: {forbidden}")
        missing.append("required setting")

    if brief.generic_tokens and _has_any(appearance, [_norm(t) for t in brief.generic_tokens]):
        reasons.append("generic person using a printer instead of the specific event workflow")
        missing.append("specific workflow")

    if brief.subject_tokens:
        if _requirement_hit(appearance, brief.subject_tokens):
            passed.append("required subject")
        else:
            missing.append("required subject")
            reasons.append("missing required subject")
    if brief.action_tokens:
        if _requirement_hit(appearance, brief.action_tokens):
            passed.append("required action")
        else:
            missing.append("required action")
            reasons.append("missing required action")
    if brief.setting_tokens:
        if "required setting" not in missing and _requirement_hit(appearance, brief.setting_tokens):
            passed.append("required setting")
        elif "required setting" not in missing:
            missing.append("required setting")
            reasons.append("missing required setting")
    for group in brief.object_token_groups:
        label = group[0] if group else "required object"
        if _requirement_hit(appearance, group):
            passed.append(label)
        else:
            missing.append(label)
            reasons.append(f"missing {label}")

    for keyword in brief.isolated_keywords:
        if _isolated_keyword_only(appearance, _norm(keyword), brief.object_token_groups + [brief.setting_tokens, brief.action_tokens]):
            reasons.append(f'isolated keyword "{keyword}" is not a complete scene match')
            if "specific workflow" not in missing:
                missing.append("specific workflow")

    planned = _norm(planned_caption)
    contradiction = _named_scene_contradiction(planned, appearance, forbidden)
    if contradiction:
        reasons.append(contradiction)
        missing.append("honest scene match")

    technical_findings = list(inspection.get("findings") or [])
    if image_path or image_bytes:
        if inspection.get("placeholder"):
            reasons.append("missing or unreadable asset")
            missing.append("readable photograph")
        if "insufficient print resolution" in technical_findings:
            reasons.append("insufficient print resolution")
            missing.append("print resolution")
        if inspection.get("watermark"):
            reasons.append("unwanted watermark")
            missing.append("clean photograph")
        sha = str(inspection.get("sha256") or "")
        if sha and other_shas and sha in other_shas:
            reasons.append("duplicate or near-duplicate of another planned photo")
            missing.append("unique photograph")
        if not inspection.get("ok") and "crop removes needed subject" in technical_findings:
            reasons.append("crop removes needed subject")
            missing.append("complete subject")
    elif not user_accepted:
        reasons.append("downloaded image was not inspected")
        missing.append("inspected photograph")

    critical_missing = [
        item
        for item in missing
        if item in {"required subject", "required action", "required setting", "specific workflow", "honest scene match"}
        or item in {group[0] for group in brief.object_token_groups if group}
    ]
    tech_ok = bool(inspection.get("ok")) if (image_path or image_bytes) else False
    contradicted = bool(
        forbidden
        or "specific workflow" in missing
        or "honest scene match" in missing
    )
    technical_reject = bool(
        "readable photograph" in missing
        or "print resolution" in missing
        or "clean photograph" in missing
        or "unique photograph" in missing
    )
    # Inspected labels that still miss a critical requirement are a hard fail.
    inspected_miss = bool(inspected_labels and critical_missing)
    hard_fail = contradicted or technical_reject or inspected_miss
    total_checks = max(len(passed) + len(set(missing)), 1)
    score = len(passed) / total_checks
    if hard_fail:
        score = min(score, 0.45)

    content_verified = bool(inspected_labels and not hard_fail and tech_ok and not critical_missing)
    required_groups_exist = bool(
        brief.subject_tokens or brief.action_tokens or brief.setting_tokens or brief.object_token_groups
    )
    internally_ready = bool(
        required_groups_exist
        and not critical_missing
        and not contradicted
        and not hard_fail
        and tech_ok
        and score >= brief.min_match_score
        and (image_path or image_bytes)
    )
    replacement = _fresh_strings(brief.search_queries) or _default_search_queries(brief)

    if hard_fail:
        status = MATCH_REJECT
        reason = "; ".join(dict.fromkeys(reasons)) or "critical requirement failed"
    elif user_accepted and tech_ok and seen_full_size:
        status = MATCH_PASS
        reason = ""
        score = max(score, brief.min_match_score)
    elif internally_ready:
        # Every required brief field passed, no contradiction, confidence cleared.
        # Internal readiness is not Visuals-stage approval.
        status = MATCH_PASS
        reason = ""
        content_verified = True
    elif content_verified and score >= brief.min_match_score and tech_ok:
        # Inspected labels confirmed the full scene. Still not metadata-only.
        status = MATCH_PASS
        reason = ""
    elif not (image_path or image_bytes):
        status = MATCH_NEEDS_REVIEW
        reason = "NEEDS USER REVIEW: photograph file was not inspected"
    elif not content_verified:
        status = MATCH_NEEDS_REVIEW
        reason = "NEEDS USER REVIEW: local content validation cannot confirm the complete scene"
        if not tech_ok and technical_findings:
            reason = "NEEDS USER REVIEW: " + "; ".join(technical_findings)
    else:
        status = MATCH_NEEDS_REVIEW
        reason = "NEEDS USER REVIEW"

    if user_accepted and status != MATCH_REJECT and tech_ok and seen_full_size:
        status = MATCH_PASS
        reason = ""

    return MatchReport(
        status=status,
        match_score=score,
        passed_requirements=passed,
        missing_requirements=list(dict.fromkeys(missing)),
        rejection_reason=reason,
        appears_to_show=appearance or "(no independent photo description)",
        required_scene=brief.required_scene(),
        technical_ok=tech_ok,
        content_verified=content_verified,
        user_accepted=bool(user_accepted),
        seen_full_size=bool(seen_full_size),
        replacement_queries=replacement,
        brief=brief.as_dict(),
    )


def evaluate_photo_aid(
    aid: dict[str, Any],
    *,
    chapter: str = "",
    title: str = "",
    topic: str = "",
    other_shas: list[str] | None = None,
) -> MatchReport:
    brief = build_visual_brief(aid, chapter=chapter, title=title, topic=topic)
    path = str(aid.get("asset_path") or aid.get("factory_asset_path") or "")
    return score_photo_against_brief(
        brief,
        alt=str(aid.get("alt") or aid.get("photo_alt") or ""),
        page_url=str(aid.get("page_url") or aid.get("source_url") or ""),
        filename=path or str(aid.get("filename") or ""),
        tags=aid.get("tags") or aid.get("keywords"),
        content_labels=aid.get("content_labels") or aid.get("inspected_labels"),
        image_path=path if path and os.path.isfile(path) else None,
        planned_caption=str(aid.get("caption") or aid.get("title") or ""),
        user_accepted=bool(aid.get("user_accepted")),
        seen_full_size=bool(aid.get("seen_full_size") or aid.get("full_size_viewed")),
        other_shas=other_shas,
    )


def apply_match_report(aid: dict[str, Any], report: MatchReport) -> dict[str, Any]:
    out = dict(aid or {})
    payload = report.as_dict()
    out["visual_brief"] = payload.get("visual_brief") or {}
    out["required_scene"] = report.required_scene
    out["appears_to_show"] = report.appears_to_show
    out["match_status"] = report.status
    out["match_score"] = report.match_score
    out["passed_requirements"] = list(report.passed_requirements)
    out["missing_requirements"] = list(report.missing_requirements)
    out["rejection_reason"] = report.rejection_reason
    out["content_verified"] = report.content_verified
    out["technical_ok"] = report.technical_ok
    out["replacement_queries"] = list(report.replacement_queries)
    out["internally_ready"] = report.status == MATCH_PASS
    if report.status != MATCH_PASS:
        out["approved"] = False
        out["internally_ready"] = False
    if report.status == MATCH_REJECT:
        out["internally_ready"] = False
        out["user_accepted"] = False
    if report.status == MATCH_NEEDS_REVIEW:
        out["review_status"] = "NEEDS USER REVIEW"
    elif report.status == MATCH_REJECT:
        out["review_status"] = "REJECTED"
    else:
        out["review_status"] = "MATCHED"
    return out


def stamp_plan_photo_matches(visual_plan: dict | None) -> dict:
    plan = visual_plan if isinstance(visual_plan, dict) else {"chapters": []}
    shas: list[str] = []
    for ch in list(plan.get("chapters") or []):
        if not isinstance(ch, dict):
            continue
        for aid in list(ch.get("aids") or []):
            if isinstance(aid, dict) and str(aid.get("type") or "").lower() in {"photo", "stock photo"}:
                sha = str(aid.get("sha256") or "")
                if sha:
                    shas.append(sha)
    seen: dict[str, int] = {}
    for ch in list(plan.get("chapters") or []):
        if not isinstance(ch, dict):
            continue
        chapter = str(ch.get("chapter") or "")
        aids = list(ch.get("aids") or [])
        for i, aid in enumerate(aids):
            if not isinstance(aid, dict):
                continue
            if str(aid.get("type") or "").lower() not in {"photo", "stock photo"}:
                continue
            sha = str(aid.get("sha256") or "")
            others = [s for s in shas if s and s != sha]
            if sha:
                seen[sha] = seen.get(sha, 0) + 1
                if seen[sha] > 1:
                    others = [sha]
            snapshot = json.loads(json.dumps(aid))
            report = evaluate_photo_aid(snapshot, chapter=chapter, other_shas=others)
            aids[i] = apply_match_report(aid, report)
        ch["aids"] = aids
    return plan


def photo_blocks_approval(aid: dict[str, Any] | None) -> str:
    if not isinstance(aid, dict):
        return ""
    if str(aid.get("type") or "").lower() not in {"photo", "stock photo"}:
        return ""
    status = str(aid.get("match_status") or "")
    if not status:
        report = evaluate_photo_aid(aid)
        status = report.status
        reason = report.rejection_reason
    else:
        reason = str(aid.get("rejection_reason") or "")
    if status == MATCH_PASS:
        return ""
    if status == MATCH_REJECT:
        return reason or "Photograph failed the structured visual brief."
    return reason or "NEEDS USER REVIEW"


def candidate_search_queries(brief: VisualBrief, *, failed_queries: list[str] | None = None) -> list[str]:
    failed = {_norm(q) for q in (failed_queries or []) if str(q).strip()}
    out: list[str] = []
    for query in _fresh_strings(brief.search_queries) or _default_search_queries(brief):
        if _norm(query) in failed:
            continue
        if query not in out:
            out.append(query)
    return out


def contains_customer_source_url(text: str) -> bool:
    blob = str(text or "")
    for match in _URL_RE.findall(blob):
        host = (urlparse(match).hostname or "").lower()
        if _SOURCE_HOST_RE.search(host or match):
            return True
    return bool(_SOURCE_HOST_RE.search(blob) and "http" in blob.lower())


def strip_customer_source_urls(text: str) -> str:
    cleaned = _URL_RE.sub("", str(text or ""))
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def customer_source_label(aid: dict[str, Any] | None) -> str:
    """Customer-facing source label. Never a URL."""
    row = aid if isinstance(aid, dict) else {}
    source = str(row.get("source") or "").strip().lower()
    kind = str(row.get("type") or "").strip().lower()
    if source in {"ai", "ai_generated", "dall-e", "dalle"} or kind in {"ai image", "ai-created image"}:
        return "AI-created image"
    if kind in {"photo", "stock photo"} or source in {"pexels", "stock", "stock photo"}:
        return "Stock photo"
    return "Factory-created graphic"


def customer_visual_description(aid: dict[str, Any] | None) -> str:
    row = aid if isinstance(aid, dict) else {}
    text = str(row.get("caption") or row.get("title") or row.get("business_purpose") or "").strip()
    text = strip_customer_source_urls(text)
    if not text:
        return "Chapter visual prepared for this ebook."
    sentence = text.split(".")[0].strip()
    return sentence[:180] or "Chapter visual prepared for this ebook."


def customer_safe_visual_plan(visual_plan: dict | None) -> dict[str, Any]:
    """Copy used in customer PDF/ZIP. Keeps attribution text; drops source URLs."""
    plan = json.loads(json.dumps(visual_plan if isinstance(visual_plan, dict) else {"chapters": []}))
    drop = {
        "page_url",
        "source_url",
        "photographer_url",
        "preview_url",
        "original_url",
        "preview_data_uri",
        "thumb_data_uri",
        "pexels_query",
        "replacement_queries",
        "failed_queries",
        "rejected_photo_ids",
    }
    for ch in list(plan.get("chapters") or []):
        if not isinstance(ch, dict):
            continue
        for aid in list(ch.get("aids") or []):
            if not isinstance(aid, dict):
                continue
            for key in list(drop):
                aid.pop(key, None)
            for key in ("caption", "title", "attribution", "appears_to_show"):
                if key in aid:
                    aid[key] = strip_customer_source_urls(str(aid.get(key) or ""))
    return plan


def score_pexels_candidate(brief: VisualBrief, photo: dict[str, Any]) -> MatchReport:
    return score_photo_against_brief(
        brief,
        alt=str(photo.get("alt") or ""),
        page_url=str(photo.get("page_url") or photo.get("url") or ""),
        filename=str(photo.get("photo_id") or ""),
        tags=photo.get("tags"),
        planned_caption="",
    )


def rank_pexels_candidates(
    brief: VisualBrief,
    photos: list[dict[str, Any]],
    *,
    rejected_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Score every candidate. Rejected photos never rank. Passing photos rank first."""
    skipped: list[dict[str, Any]] = []
    blocked = {str(x) for x in (rejected_ids or set())}
    ranked: list[tuple[bool, float, dict[str, Any]]] = []
    for photo in photos or []:
        if not isinstance(photo, dict):
            continue
        pid = str(photo.get("photo_id") or photo.get("id") or "")
        if pid and pid in blocked:
            skipped.append({**photo, "rejection_reason": "previously rejected"})
            continue
        report = score_pexels_candidate(brief, photo)
        photo = dict(photo)
        photo["match_status"] = report.status
        photo["match_score"] = report.match_score
        photo["rejection_reason"] = report.rejection_reason
        photo["appears_to_show"] = report.appears_to_show
        if report.status == MATCH_REJECT:
            skipped.append(photo)
            continue
        ranked.append((report.status == MATCH_PASS, float(report.match_score), photo))
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [row[2] for row in ranked], skipped


def pick_pexels_candidate(
    brief: VisualBrief,
    photos: list[dict[str, Any]],
    *,
    rejected_ids: set[str] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    ranked, skipped = rank_pexels_candidates(brief, photos, rejected_ids=rejected_ids)
    return (ranked[0] if ranked else None), skipped


def score_local_candidates(
    brief: VisualBrief,
    candidate_dir: str | Path,
    *,
    index_name: str = "index.json",
) -> list[dict[str, Any]]:
    root = Path(candidate_dir)
    index_path = root / index_name
    rows: list[dict[str, Any]] = []
    if index_path.is_file():
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        results = payload.get("results") if isinstance(payload, dict) else None
        if isinstance(results, dict):
            for items in results.values():
                if isinstance(items, list):
                    rows.extend(item for item in items if isinstance(item, dict))
        elif isinstance(payload, list):
            rows = [item for item in payload if isinstance(item, dict)]
    scored: list[dict[str, Any]] = []
    for row in rows:
        pid = str(row.get("photo_id") or "")
        path = root / f"ch7_{pid}.jpg"
        if not path.is_file():
            path = root / f"ch7_{pid}.png"
        report = score_photo_against_brief(
            brief,
            alt=str(row.get("alt") or ""),
            page_url=str(row.get("page_url") or ""),
            filename=str(path),
            image_path=str(path) if path.is_file() else None,
            planned_caption="",
        )
        scored.append(
            {
                "photo_id": pid,
                "path": str(path) if path.is_file() else "",
                "page_url": row.get("page_url") or "",
                "photographer": row.get("photographer") or "",
                "attribution": row.get("attribution") or "",
                "query": row.get("query") or "",
                **report.as_dict(),
            }
        )
    scored.sort(key=lambda item: (item.get("match_status") == MATCH_PASS, item.get("match_score") or 0), reverse=True)
    return scored
