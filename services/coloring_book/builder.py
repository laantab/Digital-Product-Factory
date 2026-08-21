"""Coloring Book Builder — generates line-art page prompts and images."""
from __future__ import annotations

import os
import random
import re
from dataclasses import dataclass, field

from ai_client import chat_json
from services.coloring_book.quality_agent import validate_coloring_book_pages
from services.coloring_book.prompt_engine import (
    COLORING_NEGATIVE_PROMPT,
    COVER_NEGATIVE_PROMPT,
    SUPPORTS_REFERENCE_IMAGE_CONDITIONING,
    build_character_bible,
    build_cover_image_prompt,
    build_local_story_pages,
    derive_cover_copy,
    finalize_interior_prompt,
    is_bank_rescue_theme,
    is_farm_theme,
    is_superhero_narrative,
    uses_comic_line_art,
    validate_cover_prompt_lock,
    validate_locked_prompts,
)
from services.ebook_package import generate_visual_image


def _is_image_ai_available() -> bool:
    """Check whether image-generation AI is available."""
    try:
        from ai_client import get_client
        get_client()
        return True
    except Exception:
        return False

EXPORTS_DIR = os.environ.get(
    "FLASK_EXPORTS_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "exports"),
)


@dataclass
class ColoringPageResult:
    page_number: int
    topic: str  # short page title e.g. "Happy Dinosaur"
    line_art_prompt: str  # detailed line-art prompt for AI image generator
    caption: str = ""  # optional one-line caption at bottom of page
    image_path: str = ""  # local path to generated PNG if available

    def as_dict(self) -> dict:
        return {
            "page_number": self.page_number,
            "topic": self.topic,
            "line_art_prompt": self.line_art_prompt,
            "caption": self.caption,
            "image_path": self.image_path,
        }


@dataclass
class ColoringBookResult:
    product_title: str
    subtitle: str
    pages: list[ColoringPageResult]
    cover_prompt: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    image_failures: list[int] = field(default_factory=list)  # page numbers that failed
    quality_result: dict | None = None  # result from ColoringBookQualityResult.as_dict()
    generation_stage: str = "full"
    character_bible: dict | None = None
    reference_image_path: str = ""
    consistency_notes: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return bool(self.pages)

    @property
    def quality_passed(self) -> bool:
        return bool(self.quality_result and self.quality_result.get("all_passed", False))

    def as_dict(self) -> dict:
        return {
            "product_title": self.product_title,
            "subtitle": self.subtitle,
            "pages": [p.as_dict() for p in self.pages],
            "cover_prompt": self.cover_prompt,
            "warnings": self.warnings,
            "errors": self.errors,
            "quality_result": self.quality_result,
            "generation_stage": self.generation_stage,
            "character_bible": self.character_bible,
            "reference_image_path": self.reference_image_path,
            "consistency_notes": self.consistency_notes,
        }


def _extract_keywords_from_theme(theme: str) -> list[str]:
    """
    Extract key phrases from the user's theme that should appear in generated pages.

    Priority: longest match first (prevents partial-word extraction from
    over-writing complete names like "Thunder Volt" with "thunder").

    Focus on:
    - Character names: "Thunder Volt", "named Thunder Volt"
    - Locations: "New York City", "Paris"
    - Identity: "Black superhero"
    Returns deduplicated list of lowercased phrases (1-4 words).
    """
    keywords = []
    seen = set()

    def add(kw):
        kw = str(kw).strip().lower()
        if kw and kw not in seen and len(kw) > 2:
            seen.add(kw)
            keywords.append(kw)

    # 1. Quoted strings — highest priority, preserves exact multi-word names
    for q in re.findall(r'"([^"]+)"', theme):
        add(q)

    # 2. "named Thunder Volt" / "called [Name]" / "known as [Name]"
    named_m = re.search(
        r'\b(?:named|called|known as)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})',
        theme
    )
    if named_m:
        add(named_m.group(1))

    # 3. Location: "in/at/on/inside [City Name]" — extract up to 4-word city
    loc_m = re.search(
        r'\b(?:in|at|on|inside|around|near|across|from)\s+'
        r'([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})',
        theme
    )
    if loc_m:
        loc = loc_m.group(1).strip()
        if len(loc) > 2:
            add(loc)

    # 4. Identity phrase: "Black superhero" / "Red dragon" / "Green witch"
    # Pattern: color word + common hero/fantasy role
    identity_m = re.findall(
        r'\b(Black|White|Red|Green|Blue|Golden|Silver|Dark|Mighty|Great)\s+'
        r'(superhero|hero|villain|knight|dragon|witch|wizard|king|queen|warrior|master|sage)\b',
        theme, re.IGNORECASE
    )
    for adj, noun in identity_m:
        add(f"{adj.lower()} {noun.lower()}")

    # 5. Two-word ALL-CAPS hero names: "THUNDER VOLT"
    caps_two = re.findall(r'\b([A-Z]{2,})\s+([A-Z]{2,})\b', theme)
    for w1, w2 in caps_two:
        add(f"{w1.lower()} {w2.lower()}")

    # 6. Two-word title-case name: "Thunder Volt" (not at start of sentence)
    # Preceded by non-alphanumeric, min 3 chars each
    two_word = re.findall(
        r'(?<=[^A-Za-z])([A-Z][a-z]{2,20})\s+([A-Z][a-z]{2,20})(?=[^a-zA-Z]|$)',
        theme
    )
    for w1, w2 in two_word:
        add(f"{w1.lower()} {w2.lower()}")

    # 7. Three-word title-case: "New York City"
    three_word = re.findall(
        r'(?<=[^A-Za-z])([A-Z][a-z]{2,20})\s+([A-Z][a-z]{2,20})\s+([A-Z][a-z]{2,20})(?=[^a-zA-Z]|$)',
        theme
    )
    for w1, w2, w3 in three_word:
        add(f"{w1.lower()} {w2.lower()} {w3.lower()}")

    # 8. Single title-case word (not at string start, not already added, skip noise)
    single_word = re.findall(
        r'(?<=[^A-Za-z])([A-Z][a-z]{2,20})(?=[^a-zA-Z]|$)',
        theme
    )
    skip = {
        'the', 'and', 'for', 'with', 'from', 'this', 'that', 'your', 'they',
        'were', 'have', 'been', 'being', 'would', 'could', 'should',
        'will', 'shall', 'does', 'just', 'very', 'also', 'even', 'than',
        'then', 'when', 'what', 'where', 'which', 'while', 'about', 'after',
        'before', 'between', 'into', 'over', 'under', 'again', 'once',
        'here', 'there', 'each', 'both', 'most', 'some', 'such', 'only',
        'same', 'said', 'one', 'two', 'got', 'let', 'see', 'know', 'way',
        'gets', 'away', 'named', 'city', 'bank', 'robs', 'stops', 'escapes',
    }
    for w in single_word:
        w_lc = w.lower()
        if w_lc not in seen and w_lc not in skip and len(w_lc) > 3:
            add(w_lc)

    return keywords


def validate_theme_adherence(theme: str, pages: list, cover_prompt: str = "") -> tuple[bool, list[str]]:
    """
    Validate that generated pages honour the user's full theme.

    Returns (passed: bool, missing_keywords: list[str]).

    Algorithm:
      1. Extract key phrases from the user's theme (names, code-names, locations).
      2. Scan each page's topic + line_art_prompt for those keywords (substring match).
      3. Also scan the cover_prompt.
      4. A keyword is "covered" if:
         - it appears in >= 1 page AND appears in cover_prompt, OR
         - it appears in >= 25% of pages (lenient for short books), OR
         - it appears in cover_prompt (strong signal — cover is always required)
      5. A keyword is MISSING only if it appears in < 1 page AND not in cover_prompt.
      6. Validation FAILS if any keyword is missing from both pages AND cover.

    This prevents generic substitutions: e.g. "Thunder Volt" must appear in the
    generated pages or cover, not be silently replaced with a generic "Superhero".
    """
    if not theme or not pages:
        return True, []

    keywords = _extract_keywords_from_theme(theme)
    if not keywords:
        return True, []

    total = len(pages)
    missing = []

    for keyword in keywords:
        # Count how many pages mention this keyword (case-insensitive substring)
        page_hits = 0
        for page in pages:
            combined = (
                page.get("topic", "")
                + " "
                + page.get("line_art_prompt", "")
            ).lower()
            if keyword.lower() in combined:
                page_hits += 1

        cover_hit = keyword.lower() in cover_prompt.lower() if cover_prompt else False
        # A keyword passes if:
        # - it appears in at least 1 page (25% threshold for 4-page book), OR
        # - it appears in the cover (strong enough to pass)
        covered = page_hits >= 1 or cover_hit

        if not covered:
            missing.append(keyword)

    passed = len(missing) == 0
    return passed, missing


def _parse_coloring_book_response(raw: dict | str, page_count: int) -> list[dict]:
    """Extract page entries from AI JSON response.

    Handles both the requested format (topic/line_art_prompt/caption)
    and the actual format the model often returns (title/description/elements).
    """
    if isinstance(raw, str):
        # Try to extract JSON from markdown code block
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if match:
            try:
                import json as _json

                raw = _json.loads(match.group(1))
            except Exception:
                pass

    pages_data = raw if isinstance(raw, dict) else {}
    pages_list = pages_data.get("pages", [])
    if not isinstance(pages_list, list):
        pages_list = []

    # Normalize field names from whatever the model returned
    normalized = []
    for entry in pages_list:
        if not isinstance(entry, dict):
            continue
        # Build line_art_prompt from whatever fields are available
        desc = str(entry.get("description") or entry.get("line_art_prompt") or "").strip()
        elements = entry.get("elements", [])
        if elements and not desc:
            # Build prompt from elements list
            element_strs = []
            for el in (elements if isinstance(elements, list) else []):
                if isinstance(el, dict):
                    name = el.get("element", "")
                    el_desc = el.get("description", "")
                    element_strs.append(f"{name}: {el_desc}" if el_desc else name)
                elif isinstance(el, str):
                    element_strs.append(el)
            desc = "; ".join(element_strs)

        page_title = str(entry.get("topic") or entry.get("title") or f"Page {len(normalized)+1}").strip()
        normalized.append({
            "topic": page_title,
            "line_art_prompt": desc or f"A detailed line-art coloring page of {page_title}.",
            "caption": str(entry.get("caption", "")),
        })
    return normalized


# ---------------------------------------------------------------------------
# Local deterministic page planner — no AI required
# ---------------------------------------------------------------------------

def _local_page_planner(
    theme: str,
    page_count: int,
    age_group: str,
    art_style: str,
    main_character: str,
    include_captions: bool,
    setting: str = "",
) -> tuple[list[dict], str]:
    """
    Generate page concepts deterministically from the theme/title, no AI needed.
    Returns (pages_list, cover_prompt).
    """
    theme = str(theme or "Coloring Book").strip()
    main_char = str(main_character or "").strip()
    # Bank-rescue OR farm (and other theme-bible stories) use authoritative scene bible.
    # Farm must never fall into the superhero topic list.
    if is_bank_rescue_theme(theme) or is_farm_theme(theme):
        pages, cover_prompt, _bible, _cover = build_local_story_pages(
            theme,
            page_count,
            main_character=main_char,
            setting=setting,
            art_style=art_style,
            include_captions=include_captions,
        )
        return pages, cover_prompt

    if is_superhero_narrative(theme, main_char, art_style) and any(
        k in theme.lower() for k in ("bank", "robber", "new york", "thunder volt", "superhero")
    ):
        pages, cover_prompt, _bible, _cover = build_local_story_pages(
            theme,
            page_count,
            main_character=main_char,
            setting=setting,
            art_style=art_style,
            include_captions=include_captions,
        )
        return pages, cover_prompt

    # Build a character anchor for page topics
    char_label = main_char or _extract_noun(theme)
    age = str(age_group or "").lower()
    style = str(art_style or "").lower()

    # Determine age tier
    is_kids = any(w in age for w in ["kids", "children", "6-8", "8-10", "all ages"])
    is_teens = any(w in age for w in ["teen", "12-adult", "12-14", "tween"])
    is_adult = "adult" in age

    # Determine art style
    is_cartoon = any(w in style for w in ["cartoon", "cute", "bold", "comic"])
    is_realistic = any(w in style for w in ["realistic", "detailed adult", "adult detailed"])
    # Comic line-art wrappers that inject Thunder Volt locks: only for true bank-rescue.
    comic_line = is_bank_rescue_theme(theme) and uses_comic_line_art(theme, art_style, main_char)

    # ── Superhero / action theme detection (theme text only — never art style) ──
    is_superhero = (not is_farm_theme(theme)) and (
        is_superhero_narrative(theme, main_char, "")
        or any(
            kw in theme.lower()
            for kw in [
                "thunder volt", "superhero", "supervillain", "bank robber",
                "robbing a bank", "cape and",
            ]
        )
    )
    is_fantasy = any(
        kw in theme.lower()
        for kw in ["dragon", "fairy", "mermaid", "unicorn", "wizard", "enchanted", "magical", "myth", "knight", "princess", "castle", "elf"]
    )
    is_nature = any(
        kw in theme.lower()
        for kw in [
            "nature", "forest", "jungle", "ocean", "desert", "wildlife",
            "animal", "bird", "flower", "garden", "sea", "mountain",
            "butterfly", "ocean", "fish", "coral", "tree", "botanical",
            "farm", "farmer", "barn",
        ]
    )
    is_vehicle = any(
        kw in theme.lower()
        for kw in ["car", "truck", "train", "plane", "boat", "motorcycle", "vehicle", "race", "fire truck"]
    )
    is_seasonal = any(
        kw in theme.lower()
        for kw in ["christmas", "halloween", "summer", "winter", "spring", "fall", "holiday", "easter", "thanksgiving", "valentine"]
    )

    pages: list[dict] = []
    rng = random.Random(_seed_from_theme(theme))

    # ── Superhero / action theme ────────────────────────────────────────────
    if is_superhero:
        topics = [
            f"{char_label} Hero Pose with Lightning Emblem",
            f"{char_label} Flying Above the City Skyline",
            f"{char_label} Holding an Energy Shield",
            f"{char_label} Standing in a Thunderstorm",
            f"{char_label} Facing the Robot Villain",
            f"{char_label} Rescuing People at the Power Station",
            f"{char_label} Lightning Bolts Around Both Hands",
            f"{char_label} on a Rooftop at Night",
            f"{char_label} in a Comic-Style Action Scene",
            f"{char_label} with Thunder Clouds Behind Him",
            f"{char_label} Protecting the City Bridge",
            f"{char_label} Final Portrait with Bold Lightning Symbol",
            f"{char_label} Speed Burst Through the Streets",
            f"{char_label} vs. the Shadow Nemesis",
            f"{char_label} in the Secret Hero Headquarters",
            f"{char_label} Emerging from a Portal",
            f"{char_label} Deflecting Energy Blasts",
            f"{char_label} Standing on Top of a Mountain",
            f"{char_label} in a Classic Superhero Stance",
            f"{char_label} Charging Up Maximum Power",
            f"{char_label} and the Sidekick Team-Up",
            f"{char_label} Surrounded by Electric Sparks",
            f"{char_label} vs. the Alien Invasion",
            f"{char_label} at the Victory Ceremony",
        ]
        captions_map = {
            f"{char_label} Hero Pose with Lightning Emblem": "Unleash the power within!",
            f"{char_label} Flying Above the City Skyline": "The hero soars!",
            f"{char_label} Holding an Energy Shield": "Nothing gets through!",
            f"{char_label} Standing in a Thunderstorm": "Born in the storm.",
            f"{char_label} Facing the Robot Villain": "Time to save the city!",
        }
        if is_adult or is_realistic:
            topics = [t + " (detailed)" for t in topics]
        pages = _build_pages(
            topics, char_label, include_captions, captions_map, rng, page_count,
            theme=theme, art_style=art_style, comic_line=comic_line,
        )
        bible = build_character_bible(theme, main_character=main_char)
        cover = derive_cover_copy(theme)
        cover_prompt = build_cover_image_prompt(bible=bible, cover=cover)

    # ── Fantasy theme ────────────────────────────────────────────────────────
    elif is_fantasy:
        topics = [
            f"{char_label} and the Magic Sword",
            f"{char_label} Meets a Friendly Dragon",
            f"{char_label} in the Enchanted Forest",
            f"{char_label} at the Crystal Castle Gate",
            f"{char_label} Casting a Spell",
            f"{char_label} Facing the Dark Wizard",
            f"{char_label} Flying on a Unicorn",
            f"{char_label} in the Fairy Garden",
            f"{char_label} Crossing the Rainbow Bridge",
            f"{char_label} at the Mermaid Cove",
            f"{char_label} and the Treasure Chest",
            f"{char_label} Meeting the Wise Owl",
        ]
        if is_adult or is_realistic:
            topics = [t + " (detailed)" for t in topics]
        captions_map = {
            f"{char_label} and the Magic Sword": "A hero is forged.",
            f"{char_label} Meets a Friendly Dragon": "Not all dragons breathe fire.",
            f"{char_label} in the Enchanted Forest": "Magic lives here.",
        }
        pages = _build_pages(
            topics, char_label, include_captions, captions_map, rng, page_count,
            theme=theme, art_style=art_style, comic_line=comic_line,
        )
        cover_prompt = f"Fantasy portrait of {char_label} in a magical realm with dragons and castles."

    # ── Nature / wildlife theme ─────────────────────────────────────────────
    elif is_nature:
        animals = _get_nature_animals(theme)
        topics = [
            f"{char_label} in the Wild",
            f"{char_label} at Sunrise",
            f"{char_label} in the Desert",
            f"{char_label} Near the Waterfall",
            f"{char_label} in the Deep Forest",
            f"{char_label} Above the Clouds",
            f"{char_label} on a Mountain Peak",
            f"{char_label} in a Flower Field",
            f"{char_label} at the Coral Reef",
            f"{char_label} in the Savanna",
            f"{char_label} Near a Calm Lake",
            f"{char_label} in the Rainforest",
        ] + [f"{a} Portrait" for a in animals[:6]]
        if is_adult or is_realistic:
            topics = [t + " (detailed adult coloring)" for t in topics]
        captions_map = {}
        pages = _build_pages(
            topics, char_label, include_captions, captions_map, rng, page_count,
            theme=theme, art_style=art_style, comic_line=comic_line,
        )
        cover_prompt = f"Nature coloring book cover: {char_label} in a beautiful natural setting."

    # ── Vehicle theme ───────────────────────────────────────────────────────
    elif is_vehicle:
        topics = [
            f"{char_label} Racing Down the Track",
            f"{char_label} Crossing the Bridge",
            f"{char_label} in the City Traffic",
            f"{char_label} on the Open Highway",
            f"{char_label} at the Race Start Line",
            f"{char_label} Performing a Stunt",
            f"{char_label} in the Garage",
            f"{char_label} in a Vintage Style",
            f"{char_label} Off-Road Adventure",
            f"{char_label} at Sunset Cruise",
            f"{char_label} on a Mountain Road",
            f"{char_label} in the Night City",
        ]
        if is_adult or is_realistic:
            topics = [t + " (detailed)" for t in topics]
        captions_map = {}
        pages = _build_pages(
            topics, char_label, include_captions, captions_map, rng, page_count,
            theme=theme, art_style=art_style, comic_line=comic_line,
        )
        cover_prompt = f"Action vehicle coloring book cover featuring {char_label}."

    # ── Seasonal theme ──────────────────────────────────────────────────────
    elif is_seasonal:
        topics = [
            f"{char_label} Celebrating the Season",
            f"{char_label} in a Festive Scene",
            f"{char_label} with Seasonal Decorations",
            f"{char_label} in a Winter Wonderland",
            f"{char_label} at a Seasonal Festival",
            f"{char_label} Sharing the Joy",
            f"{char_label} in a Cozy Setting",
            f"{char_label} in a Traditional Scene",
            f"{char_label} with Friends",
            f"{char_label} in Full Costume",
            f"{char_label} in the Snow",
            f"{char_label} with Gifts and Treats",
        ]
        if is_adult or is_realistic:
            topics = [t + " (detailed)" for t in topics]
        captions_map = {}
        pages = _build_pages(
            topics, char_label, include_captions, captions_map, rng, page_count,
            theme=theme, art_style=art_style, comic_line=comic_line,
        )
        cover_prompt = f"Seasonal coloring book cover featuring {char_label} in a festive scene."

    # ── Default / generic theme ─────────────────────────────────────────────
    else:
        topics = _get_generic_topics(char_label, page_count, is_kids, is_adult, is_realistic)
        if is_cartoon and not is_adult:
            topics = [t + " (cartoon style)" for t in topics]
        captions_map = {}
        pages = _build_pages(
            topics, char_label, include_captions, captions_map, rng, page_count,
            theme=theme, art_style=art_style, comic_line=comic_line,
        )
        cover_prompt = f"Coloring book cover for '{theme}' — {char_label} in an engaging scene."

    return pages, cover_prompt


def _kawaii_line_art_wrapper(topic: str) -> str:
    return (
        f"Create a professional Bold & Easy Kawaii Coloring Page featuring {topic}.\n\n"
        "The image may be generated on a square canvas if required by the image model, "
        "but the final printable page must be an 8.5 x 11 inch portrait coloring page. "
        "The artwork must be scaled proportionally to fill the printable page as much as possible "
        "while keeping all content visible within safe margins.\n\n"
        "Use a cute kawaii style with bold clean black outlines, consistent line weight, "
        "simple rounded shapes, friendly features, and large open coloring spaces.\n\n"
        "The artwork must have:\n"
        "- pure white background\n"
        "- black line art only\n"
        "- no gray\n"
        "- no shading\n"
        "- no shadows\n"
        "- no texture\n"
        "- no cross-hatching\n"
        "- no stippling\n"
        "- no border\n"
        "- no frame\n"
        "- no decorative outline around the image edges\n"
        "- no top edge line (no horizontal line spanning the full width at the top)\n"
        "- no bottom edge line (no horizontal line spanning the full width at the bottom)\n"
        "- no left edge line (no vertical line spanning the full height on the left side)\n"
        "- no right edge line (no vertical line spanning the full height on the right side)\n"
        "- no text\n"
        "- no letters\n"
        "- no numbers\n"
        "- no watermark\n"
        "- no logo\n\n"
        "Do not leave the subject tiny in the center. Do not crop the subject. "
        "Do not add top or bottom blank title areas. Do not draw a decorative rectangle, "
        "a decorative frame, a decorative page border, a top edge line, a bottom edge line, "
        "a left edge line, or a right edge line. "
        "The subject's natural outlines and silhouettes are fine — but no enclosing lines around the perimeter of the canvas. "
        "The final result must look like a clean, professional, commercial-quality printable coloring page."
    )


def _build_pages(
    topic_pool: list[str],
    char_label: str,
    include_captions: bool,
    captions_map: dict[str, str],
    rng: random.Random,
    page_count: int,
    *,
    theme: str = "",
    art_style: str = "",
    comic_line: bool = False,
) -> list[dict]:
    """Build exactly page_count page entries from the topic pool."""
    pool = topic_pool[:]
    rng.shuffle(pool)
    # Repeat and cycle if needed
    while len(pool) < page_count:
        pool += topic_pool[: page_count - len(pool)]
    selected = pool[:page_count]
    pages = []
    bible = build_character_bible(theme, main_character=char_label) if theme else None
    for i, topic in enumerate(selected):
        caption = ""
        if include_captions:
            caption = captions_map.get(topic, f"{char_label} — page {i+1}")
        if comic_line and bible:
            prompt = finalize_interior_prompt(
                f"Scene: {topic}. Feature {char_label} with adult comic-book proportions.",
                bible,
                art_style,
            )
        else:
            prompt = _kawaii_line_art_wrapper(topic)
        pages.append({
            "topic": topic,
            "line_art_prompt": prompt,
            "caption": caption,
        })
    return pages


def _extract_noun(theme: str) -> str:
    """Extract the most meaningful noun from the theme as a character label."""
    # Superhero patterns
    m = re.search(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b",
        theme,
    )
    if m:
        return m.group(1)
    # Fallback: first two capitalized words or first word
    words = re.findall(r"[A-Za-z]+", theme)
    for w in reversed(words):
        if len(w) > 2:
            return w.title()
    return theme.title() or "Coloring Page"


def _seed_from_theme(theme: str) -> int:
    """Deterministic seed from theme string."""
    return sum(ord(c) for c in (theme or "coloring")) % (2**31)


def _get_nature_animals(theme: str) -> list[str]:
    t = theme.lower()
    if "desert" in t:
        return ["Camel", "Rattlesnake", "Horned Lizard", "Road Runner", "Scorpion", "Fennec Fox", "Jackrabbit", "Gila Monster"]
    if "ocean" in t or "sea" in t:
        return ["Dolphin", "Sea Turtle", "Shark", "Whale", "Octopus", "Jellyfish", "Seahorse", "Manta Ray"]
    if "jungle" in t or "rainforest" in t:
        return ["Toucan", "Jaguar", "Monkey", "Sloth", "Crocodile", "Parrot", "Poison Dart Frog", "Orangutan"]
    if "forest" in t or "woodland" in t:
        return ["Bear", "Deer", "Fox", "Owl", "Rabbit", "Wolf", "Raccoon", "Squirrel"]
    if "bird" in t or "avian" in t:
        return ["Eagle", "Hawk", "Falcon", "Owl", "Cardinal", "Blue Jay", "Pelican", "Flamingo"]
    return ["Lion", "Tiger", "Elephant", "Giraffe", "Zebra", "Monkey", "Eagle", "Wolf"]


def _get_generic_topics(
    char_label: str,
    page_count: int,
    is_kids: bool,
    is_adult: bool,
    is_realistic: bool,
) -> list[str]:
    """Generic fallback topics based on character label and age/style."""
    if is_kids:
        base = [
            f"{char_label} at the Playground",
            f"{char_label} Playing with Friends",
            f"{char_label} at the Beach",
            f"{char_label} in the Backyard",
            f"{char_label} at the Zoo",
            f"{char_label} Baking in the Kitchen",
            f"{char_label} Reading a Book",
            f"{char_label} at a Birthday Party",
            f"{char_label} Going on a Picnic",
            f"{char_label} Riding a Bike",
            f"{char_label} at the Farm",
            f"{char_label} Playing Dress-Up",
            f"{char_label} Building a Sandcastle",
            f"{char_label} Flying a Kite",
            f"{char_label} at the Amusement Park",
        ]
    elif is_adult or is_realistic:
        base = [
            f"{char_label} Portrait Study",
            f"{char_label} in a Detailed Scene",
            f"{char_label} Complex Pattern Page",
            f"{char_label} Mandala-Style Design",
            f"{char_label} with Intricate Background",
            f"{char_label} Full-Page Detailed Illustration",
            f"{char_label} with Geometric Patterns",
            f"{char_label} Nature-Inspired Design",
            f"{char_label} with Floral Elements",
            f"{char_label} Architectural Detail Study",
            f"{char_label} Still Life Composition",
            f"{char_label} with Celtic Knotwork",
            f"{char_label} Abstract Pattern",
            f"{char_label} Decorative Border Design",
            f"{char_label} Elaborate Scene",
        ]
    else:
        base = [
            f"{char_label} in an Action Pose",
            f"{char_label} with a Best Friend",
            f"{char_label} at the Park",
            f"{char_label} Cooking Something Delicious",
            f"{char_label} Playing Sports",
            f"{char_label} at a Concert",
            f"{char_label} Exploring a New Place",
            f"{char_label} Doing a Hobby",
            f"{char_label} at the Beach",
            f"{char_label} Celebrating a Holiday",
            f"{char_label} Meeting New People",
            f"{char_label} in a Creative Scene",
            f"{char_label} Traveling the World",
            f"{char_label} Solving a Mystery",
            f"{char_label} as a Superhero",
        ]
    return base[:page_count] if len(base) >= page_count else (base * ((page_count // len(base)) + 1))[:page_count]


def _generate_line_art_image(
    prompt: str,
    out_path: str,
    *,
    reference_image_path: str = "",
    force: bool = False,
    package_id: str = "",
    quality: str = "medium",
) -> bool:
    """Generate one line-art image and save to out_path. Returns True on success.

    If out_path already exists (pre-generated image injected by caller), returns True
    without calling any AI — allows external image sources to bypass AI requirements.

    When the prompt already contains the authoritative character bible / comic-book
    constraints, it is sent as-is. Otherwise the legacy Bold & Easy Kawaii wrapper
    is applied for backward-compatible non-narrative themes.

    Cost controls: quality defaults to ``medium``; images.edit / retries / alternate
    sizes are disabled. ``reference_image_path`` is prompt-context only (not sent to
    images.edit). Package budgets count every images.generate attempt.
    """
    prompt = str(prompt or "").strip()
    if force and os.path.isfile(out_path):
        try:
            os.remove(out_path)
        except OSError:
            pass
    if not force and os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
        return True

    # Authoritative prompts already include style + bible — do not re-wrap/shorten.
    if (
        "CHARACTER BIBLE" in prompt
        or "THUNDER VOLT CHARACTER LOCK" in prompt
        or "American comic-book" in prompt
        or "PRODUCT STYLE" in prompt
        or "USER THEME" in prompt
        or "Bold & Easy Kawaii Coloring Page" in prompt
    ):
        line_art_prompt = prompt
    else:
        line_art_prompt = _kawaii_line_art_wrapper(prompt)

    # Cover path is for consistency notes / human reference only — never images.edit.
    _ = reference_image_path

    from services.ebook_package import PaidImageBudgetExceeded

    try:
        # Portrait US Letter art + long scene/bible prompts (do not truncate to 1000).
        return generate_visual_image(
            line_art_prompt,
            out_path,
            size="1024x1536",
            negative_prompt=COLORING_NEGATIVE_PROMPT,
            max_prompt_chars=4000,
            reference_image_path="",
            user_authorized=True,
            quality=quality or "medium",
            package_id=package_id or "",
            allow_edit=False,
            allow_retries=False,
        )
    except PaidImageBudgetExceeded:
        raise
    except Exception:  # noqa: BLE001
        return False


def _promote_approved_sample_interior(img_dir: str) -> str:
    """Reuse approved Stage B sample with zero paid calls.

    Prefer margin-corrected artwork when present; always leave coloring_p10.png
    as the reusable sample slot so full-stage generation skips page 10.
    """
    import shutil

    sample_slot = os.path.join(img_dir, "coloring_p10.png")
    corrected = os.path.join(img_dir, "sample_interior_margin_corrected.png")
    original = os.path.join(img_dir, "coloring_p10_original_fullres.png")
    if os.path.isfile(corrected) and os.path.getsize(corrected) > 0:
        if os.path.isfile(sample_slot) and not os.path.isfile(original):
            shutil.copy2(sample_slot, original)
        shutil.copy2(corrected, sample_slot)
        return sample_slot
    if os.path.isfile(sample_slot) and os.path.getsize(sample_slot) > 0:
        if not os.path.isfile(original):
            shutil.copy2(sample_slot, original)
        return sample_slot
    return ""


def _prepare_interior_print_assets(img_dir: str, pages: list) -> list[str]:
    """Local 300-DPI print prep for interiors that already have source PNGs."""
    from services.coloring_book.line_art_layout import prepare_print_interior_300dpi

    prepared: list[str] = []
    originals_dir = os.path.join(img_dir, "originals")
    os.makedirs(originals_dir, exist_ok=True)
    for page in pages:
        src = str(getattr(page, "image_path", "") or "")
        if not src or not os.path.isfile(src):
            continue
        page_no = int(getattr(page, "page_number", 0) or 0)
        original = os.path.join(originals_dir, f"coloring_p{page_no:02d}_original.png")
        print_path = os.path.join(img_dir, f"coloring_p{page_no:02d}_print_300dpi.png")
        prepare_print_interior_300dpi(src, print_path, original_path=original)
        page.image_path = print_path
        prepared.append(print_path)
    return prepared


def _generate_cover_image(prompt: str, out_path: str, *, force: bool = False) -> bool:
    """Generate a full-color cover image (not line art)."""
    prompt = str(prompt or "").strip()
    if force and os.path.isfile(out_path):
        try:
            os.remove(out_path)
            cover_copy = os.path.join(os.path.dirname(out_path), "cover.png")
            if os.path.isfile(cover_copy):
                os.remove(cover_copy)
        except OSError:
            pass
    if not force and os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
        return True
    try:
        return generate_visual_image(
            prompt,
            out_path,
            size="1024x1536",
            negative_prompt=COVER_NEGATIVE_PROMPT,
            max_prompt_chars=4000,
            user_authorized=True,
            quality="medium",
            allow_edit=False,
            allow_retries=False,
        )
    except Exception:  # noqa: BLE001
        return False


def build_coloring_book(
    *,
    theme: str,
    topic: str = "",
    setting: str = "",
    main_character: str = "",
    page_count: int = 12,
    age_group: str = "",
    art_style: str = "",
    product_title: str = "",
    subtitle: str = "",
    include_captions: bool = False,
    package_id: str = "",
    seed: int | None = None,
    # Quality mode: "ai_image_coloring_page" (AI images required) or "basic_test" (local fallback OK)
    quality_mode: str = "ai_image_coloring_page",
    # Creation modes
    creation_mode: str = "theme",  # "market_research" | "scratch" | "theme"
    # Benchmark data (market research mode)
    benchmark_niche: str = "",
    benchmark_audience: str = "",
    benchmark_reason: str = "",
    # Staged generation: cover_preview | sample_interior | full
    generation_stage: str = "full",
    character_approved: bool = False,
    sample_approved: bool = False,
    reference_image_path: str = "",
    force_image_regen: bool = False,
) -> ColoringBookResult:
    """
    Generate coloring book pages with line-art prompts.
    Supports 3 creation modes:
      - market_research: replicate the winning format of a benchmark bestseller
      - scratch: custom title + character + theme
      - theme: existing theme-based generation
    Quality modes:
      - ai_image_coloring_page: requires AI image generation; raises error if unavailable
      - basic_test: uses local procedural fallback for pages; no AI images required
    Attempts AI image generation for each page; falls back gracefully in basic_test mode.
    """
    # Preserve the user's full theme — never shorten/replace/generalize it.
    theme = str(theme or "Coloring Book").strip()
    topic = str(topic or "").strip()
    setting = str(setting or "").strip()
    main_character = str(main_character or "").strip()
    bible = build_character_bible(theme, main_character=main_character, setting=setting)
    if not main_character:
        main_character = bible.hero_name
    cover_copy = derive_cover_copy(theme, product_title=product_title, subtitle=subtitle)
    # Short display title — never dump the full theme sentence into headers/cover title
    if product_title and str(product_title).strip() and str(product_title).strip().lower() != theme.lower():
        title = str(product_title).strip()
        if len(title) > 48 or " is " in title.lower():
            title = cover_copy.title
    else:
        title = cover_copy.title
    subtitle = str(subtitle or cover_copy.subtitle or "").strip()
    art_clause = f" Art style: {art_style}." if art_style else ""
    age_clause = f" Target age group: {age_group}." if age_group else ""
    caption_clause = (
        " Include a short caption for every page (displayed below the image on the page)."
        if include_captions
        else " Do not include captions."
    )
    topic_clause = f" Book topic: {topic}." if topic and topic != theme else ""
    setting_clause = f" Setting: {setting}." if setting else ""
    char_clause = (
        f" Main character: {main_character}. Every page should feature {main_character} "
        "in a different scene or situation."
        if main_character
        else ""
    )
    comic_line = uses_comic_line_art(theme, art_style, main_character)
    narrative_bank = is_bank_rescue_theme(theme)
    narrative_farm = is_farm_theme(theme)

    if comic_line:
        system = (
            "You are an adult superhero coloring-book creator who writes vivid, "
            "drawable American comic-book black-and-white line-art prompts. "
            "Preserve the user's full theme exactly — do not shorten, replace, or generalize it. "
            "Every page must include the character bible (hero + two distinguishable robbers). "
            "Adult proportions, clean outlines, large open coloring areas, white background. "
            "No color, gray, shading, gradients, solid-black costume fills, tiny cross-hatch, "
            "gore, guns, text, speech bubbles, watermarks, or copyrighted characters."
        )
    else:
        system = (
            "You are a children's and adult coloring-book creator who writes vivid, "
            "drawable line-art prompts. All pages use the Bold & Easy Kawaii style: "
            "cute kawaii illustrations with simple rounded shapes, bold clean outlines, "
            "consistent line weight, large open coloring areas, and friendly features. "
            "Pages must be distinct and non-repetitive. "
            "IMPORTANT style rules for every prompt: "
            "bold and easy, cute kawaii, simple rounded shapes, clean black line art, "
            "large open spaces, clear subject separation, not crowded, not too empty. "
            "No shading, no gray, no color, no realistic rendering, no tiny details, no clutter. "
            "Preserve the user's full theme — do not shorten, replace, or generalize it."
        )

    mode = str(creation_mode or "theme").lower()

    if mode == "market_research" and benchmark_niche:
        # Replicate a benchmark bestseller's winning format
        niche_clause = f"Benchmark bestseller niche: {benchmark_niche}."
        audience_clause = f"Target audience: {benchmark_audience}." if benchmark_audience else ""
        reason_clause = (
            f"Why it wins: {benchmark_reason}" if benchmark_reason else ""
        )
        user = (
            f"Create a {page_count}-page coloring book plan in JSON.\n\n"
            f"IMPORTANT — replicate the winning format of this bestseller:\n"
            f"{niche_clause}\n"
            f"{audience_clause}\n"
            f"{reason_clause}\n\n"
            f"Your book must follow the same format, theme, and style that makes "
            f"this bestseller successful — but with your own unique spin.\n"
            f"Number of pages: {page_count}\n"
            f"{age_clause}\n"
            f"{art_clause}\n"
            f"{caption_clause}\n\n"
            "Return a JSON object with exactly this shape:\n"
            "{\n"
            '  "title": "string — book title inspired by the winning format",\n'
            '  "subtitle": "string — short subtitle",\n'
            '  "pages": [\n'
            "    {\n"
            '      "topic": "string — short page title",\n'
            '      "line_art_prompt": "string — detailed line-art prompt (specific about subject, pose, setting, style)",\n'
            '      "caption": "string — short caption (only if include_captions is true)"\n'
            "    }\n"
            "  ],\n"
            '  "cover_prompt": "string — cover line-art prompt"\n'
            "}\n\n"
            "Do not use emojis. Return only the JSON object."
        )
    elif mode == "scratch" and main_character:
        # Custom character-driven book
        subtitle_clause = f"Subtitle: {subtitle}." if subtitle else ""
        user = (
            f"Create a {page_count}-page coloring book plan in JSON featuring a recurring character.\n\n"
            f"Book title: {title}\n"
            f"{char_clause}\n"
            f"{setting_clause}\n"
            f"{topic_clause}\n"
            f"{subtitle_clause}\n"
            f"Number of pages: {page_count}\n"
            f"{age_clause}\n"
            f"{art_clause}\n"
            f"{caption_clause}\n\n"
            "Structure: Page 1 should introduce the character. Pages 2 onwards show the character "
            "in different scenes, situations, or environments — each page distinct and non-repetitive.\n\n"
            "Return a JSON object with exactly this shape:\n"
            "{\n"
            '  "title": "string — book title (use: ' + title + ')",\n'
            '  "subtitle": "string — subtitle (use: ' + subtitle + ')",\n'
            '  "pages": [\n'
            "    {\n"
            '      "topic": "string — short page title (e.g. ' + main_character + ' Meets a New Friend)",\n'
            '      "line_art_prompt": "string — detailed line-art prompt featuring ' + main_character + ' in a specific scene, be specific about what to draw, pose, setting, style)",\n'
            '      "caption": "string — short caption (only if include_captions is true)"\n'
            "    }\n"
            "  ],\n"
            '  "cover_prompt": "string — cover line-art prompt"\n'
            "}\n\n"
            "Do not use emojis. Return only the JSON object."
        )
    else:
        # Theme-based (default) — include topic, setting, and character if provided
        #
        # STRICT THEME ADHERENCE: extract mandatory details from the user's theme
        # and re-inject them as explicit instructions so the AI cannot substitute
        # or omit them.
        #
        mandatory_clause = (
            f"MANDATORY STORY DETAILS (must appear on every page):\n"
            f"  - {theme}\n"
            f"  - Do NOT shorten, replace, or generalize the user theme.\n"
            f"  - Every page must feature the character, action, and setting described above.\n"
            f"  - Do not generate unrelated scenes. Do not substitute the main character.\n"
            f"  - Character appearance must be consistent on every page.\n"
        )
        bible_clause = bible.as_prompt_block()

        # Build character-specific instruction if main_character is present
        if main_character:
            char_focus = (
                f"CHARACTER FOCUS: Every page must feature {main_character}.\n"
                f"  - Keep {main_character}'s appearance, costume, and identity identical on all pages.\n"
                f"  - Each page should show {main_character} in a different scene or situation.\n"
            )
        else:
            char_focus = (
                "CHARACTER FOCUS: If the theme describes a main character, that character\n"
                "  must appear on every page with consistent appearance and identity.\n"
            )

        user = (
            f"Create a {page_count}-page coloring book plan in JSON.\n\n"
            f"USER'S REQUIRED THEME:\n{theme}\n\n"
            f"{mandatory_clause}\n"
            f"{bible_clause}\n"
            f"{char_focus}\n"
            f"NUMBER OF PAGES: {page_count}\n"
            f"{age_clause}\n"
            f"{art_clause}\n"
            f"{caption_clause}\n\n"
            "Return a JSON object with exactly this shape:\n"
            "{\n"
            '  "title": "string — book title (must reflect the user theme above)",\n'
            '  "subtitle": "string — short subtitle",\n'
            '  "pages": [\n'
            "    {\n"
            '      "topic": "string — short page title (must advance the user theme)",\n'
            '      "line_art_prompt": "string — detailed line-art prompt for AI image generator (MUST include the user theme character, action, and setting; be specific about what to draw, pose, setting, style)",\n'
            '      "caption": "string — short caption (only if include_captions is true, otherwise empty string)"\n'
            "    }\n"
            "  ],\n"
            '  "cover_prompt": "string — FULL-COLOR cinematic comic cover prompt (must feature the user theme character and setting; no text in the art)"\n'
            "}\n\n"
            "Do not use emojis. Do not substitute a generic subject for the user theme. "
            "Every line_art_prompt must directly incorporate the USER'S REQUIRED THEME above "
            "and the CHARACTER BIBLE. "
            "Return only the JSON object."
        )

    # Authoritative story planner for bank-rescue / Thunder Volt narratives.
    # Guarantees the 12-scene sequence + character bible without AI drift.
    pages_raw: list[dict] = []
    warnings: list[str] = []
    ai_failed = False
    cover_prompt_final = build_cover_image_prompt(bible=bible, cover=cover_copy)

    if narrative_bank or narrative_farm:
        pages_raw, cover_prompt_final, bible, cover_copy = build_local_story_pages(
            theme,
            page_count,
            main_character=main_character,
            setting=setting,
            art_style=art_style,
            include_captions=include_captions,
        )
        warnings.append(
            "Using authoritative story-scene planner for the "
            + ("bank-rescue theme (character bible + fixed 12-scene sequence)."
               if narrative_bank
               else "farm theme (cover cast vs individual animal interiors).")
        )
    else:
        # Try AI planner first; fall back to local deterministic planner
        try:
            raw = chat_json(system=system, user=user, max_completion_tokens=4000)
            pages_raw = _parse_coloring_book_response(raw, page_count)
            if isinstance(raw, dict) and raw.get("cover_prompt"):
                cover_prompt_final = str(raw.get("cover_prompt") or cover_prompt_final)
        except Exception as exc:
            ai_failed = True
            if "AI is not configured" in str(exc) or "not configured" in str(exc):
                warnings.append(
                    "AI not available — using local page planner. "
                    "Pages are generated from the theme without AI assistance."
                )
            else:
                warnings.append(f"AI planner failed ({exc}) — using local page planner.")

    if not pages_raw:
        # Use local deterministic planner
        pages_raw, cover_prompt_local = _local_page_planner(
            theme=theme,
            page_count=page_count,
            age_group=age_group,
            art_style=art_style,
            main_character=main_character,
            include_captions=include_captions,
            setting=setting,
        )
        cover_prompt_final = cover_prompt_local or cover_prompt_final
        if not pages_raw:
            return ColoringBookResult(
                product_title=title,
                subtitle=subtitle,
                pages=[],
                errors=["Failed to generate coloring book page prompts."],
            )

    # Normalize to page_count entries — inject bible into every interior prompt
    pages: list[ColoringPageResult] = []
    for i in range(page_count):
        entry = pages_raw[i] if i < len(pages_raw) else pages_raw[-1] if pages_raw else {}
        page_topic = str(entry.get("topic", f"Page {i+1}")).strip()
        prompt = str(entry.get("line_art_prompt", entry.get("prompt", ""))).strip()
        caption = str(entry.get("caption", "")).strip() if include_captions else ""

        if not prompt:
            prompt = f"A detailed line-art coloring page of {page_topic}."
        prompt = finalize_interior_prompt(prompt, bible, art_style)

        pages.append(ColoringPageResult(
            page_number=i + 1,
            topic=page_topic,
            line_art_prompt=prompt,
            caption=caption,
        ))

    # Prompt-lock validation (no paid API)
    lock_issues = validate_locked_prompts([p.as_dict() for p in pages], theme)
    consistency_notes: list[str] = []
    if lock_issues:
        warnings.extend(lock_issues[:8])

    # Factory retail-cover quality lock — rebuild if AI/local cover prompt drifted.
    cover_prompt_final = cover_prompt_final or build_cover_image_prompt(
        bible=bible, cover=cover_copy
    )
    cover_lock_issues = validate_cover_prompt_lock(cover_prompt_final, theme)
    if cover_lock_issues:
        cover_prompt_final = build_cover_image_prompt(bible=bible, cover=cover_copy)
        cover_lock_issues = validate_cover_prompt_lock(cover_prompt_final, theme)
        if cover_lock_issues:
            warnings.extend([f"Cover lock: {m}" for m in cover_lock_issues[:6]])
        else:
            consistency_notes.append(
                "Cover prompt rebuilt to factory retail jumbo quality lock."
            )
    else:
        consistency_notes.append(
            "Retail jumbo cover quality lock applied (night/neon/dynamic + banner overlay)."
        )

    if narrative_bank:
        consistency_notes.append(
            "Locked Thunder Volt + Robber One/Two character bible applied to every page."
        )
        if not SUPPORTS_REFERENCE_IMAGE_CONDITIONING:
            consistency_notes.append(
                "Image service does not guarantee reference-image character conditioning; "
                "consistency relies on locked prompt text plus cover/sample approval."
            )

    stage = str(generation_stage or "full").strip().lower()
    if stage not in {"cover_preview", "sample_interior", "full"}:
        stage = "full"

    # Bank-rescue AI full books require prior cover + sample approval.
    if (
        narrative_bank
        and quality_mode == "ai_image_coloring_page"
        and stage == "full"
        and not (character_approved and sample_approved)
    ):
        return ColoringBookResult(
            product_title=title,
            subtitle=subtitle,
            pages=pages,
            cover_prompt=cover_prompt_final or build_cover_image_prompt(bible=bible, cover=cover_copy),
            warnings=warnings,
            errors=[
                "Approval required before generating all interior pages. "
                "Approve the cover character, then approve one sample interior page."
            ],
            generation_stage=stage,
            character_bible=bible.as_dict(),
            reference_image_path=reference_image_path or "",
            consistency_notes=consistency_notes,
        )

    # Try to generate images
    pkg = package_id or "coloring_book"
    img_dir = os.path.join(EXPORTS_DIR, pkg)
    os.makedirs(img_dir, exist_ok=True)

    image_failures: list[int] = []
    # Cover-as-reference helps Thunder Volt face/costume consistency, but for farm
    # (and most non-bank themes) it forces the cover cast onto every interior page.
    ref_path = ""
    if narrative_bank:
        if reference_image_path and os.path.isfile(reference_image_path):
            ref_path = reference_image_path
        else:
            candidate = os.path.join(img_dir, "img_cover.png")
            if os.path.isfile(candidate):
                ref_path = candidate

    from services.ebook_package import (
        PaidImageBudgetExceeded,
        authorize_package_image_budget,
        authorize_paid_image_generation,
        get_package_image_budget,
    )

    if quality_mode == "basic_test":
        # Basic test mode: skip AI image generation entirely; renderer uses local fallback
        for page in pages:
            page.image_path = ""  # No image file — renderer will draw local fallback
        warnings.append(
            "[BASIC TEST FALLBACK] — Not Sellable Quality. "
            "No AI image generation used. "
            "Switch to 'AI Image Coloring Page' with an image AI key for sellable output."
        )
    elif stage == "cover_preview":
        # Prompts only for interiors — cover image is generated in pdf_builder.
        for page in pages:
            page.image_path = ""
        warnings.append(
            "PAID API WARNING: Cover preview generates one full-color cover image only. "
            "Interior pages are not generated until you approve the character and a sample page."
        )
    elif stage == "sample_interior":
        # One interior for approval. Bank-rescue samples must show the hero stopping
        # both robbers (not the no-robber establishing page).
        sample_page = pages[0] if pages else None
        if narrative_bank and pages:
            preferred_topics = (
                "blocks the getaway",
                "lands on the street",
                "arrives on the scene",
                "two robbers leave the bank",
            )
            sample_page = None
            for needle in preferred_topics:
                for page in pages:
                    if needle in (page.topic or "").lower():
                        sample_page = page
                        break
                if sample_page is not None:
                    break
            if sample_page is None:
                for page in pages:
                    if "exactly two adult robbers" in (page.line_art_prompt or "").lower():
                        sample_page = page
                        break
            if sample_page is None:
                sample_page = pages[0]
        with authorize_paid_image_generation(f"coloring_book:sample_interior:{pkg}"):
            with authorize_package_image_budget(pkg, max_attempts=1, quality="medium"):
                for page in pages:
                    out_path = os.path.join(img_dir, f"coloring_p{page.page_number:02d}.png")
                    if sample_page is not None and page.page_number == sample_page.page_number:
                        page.image_path = out_path
                        ok = _generate_line_art_image(
                            page.line_art_prompt,
                            out_path,
                            reference_image_path=ref_path,
                            force=bool(force_image_regen),
                            package_id=pkg,
                            quality="medium",
                        )
                        if not ok:
                            image_failures.append(page.page_number)
                    else:
                        page.image_path = ""
        warnings.append(
            "PAID API WARNING: Sample stage generates one interior coloring page only. "
            "Remaining pages generate only after you approve the sample."
        )
    else:
        # Full book: remaining interiors only. Reuse approved cover + page-10 sample.
        warnings.append(
            "PAID API WARNING: Full-book stage generates remaining interior images via the image API "
            "(max 24 images.generate attempts, quality=medium, no retries/edits)."
        )
        if narrative_bank:
            promoted = _promote_approved_sample_interior(img_dir)
            if promoted:
                warnings.append(
                    "Reused approved Stage B sample at coloring_p10.png (0 paid calls)."
                )
            cover_path = os.path.join(img_dir, "img_cover.png")
            if os.path.isfile(cover_path):
                warnings.append("Reused approved cover img_cover.png (0 paid calls).")

        budget_max = 24 if narrative_bank else max(1, len(pages))
        try:
            with authorize_paid_image_generation(f"coloring_book:full:{pkg}"):
                with authorize_package_image_budget(
                    pkg, max_attempts=budget_max, quality="medium"
                ):
                    for page in pages:
                        out_path = os.path.join(
                            img_dir, f"coloring_p{page.page_number:02d}.png"
                        )
                        page.image_path = out_path
                        # Existing sample / prior pages short-circuit with zero API calls.
                        force = bool(force_image_regen) if (
                            narrative_farm or not narrative_bank
                        ) else False
                        if narrative_bank and os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
                            force = False
                        try:
                            ok = _generate_line_art_image(
                                page.line_art_prompt,
                                out_path,
                                reference_image_path=ref_path,
                                force=force,
                                package_id=pkg,
                                quality="medium",
                            )
                        except PaidImageBudgetExceeded as exc:
                            image_failures.append(page.page_number)
                            warnings.append(str(exc))
                            # Stop immediately — do not attempt remaining pages.
                            for rest in pages:
                                if rest.page_number > page.page_number:
                                    rest.image_path = os.path.join(
                                        img_dir, f"coloring_p{rest.page_number:02d}.png"
                                    )
                            break
                        if not ok:
                            image_failures.append(page.page_number)
                            # Stop on first failed generation — no automatic retry.
                            warnings.append(
                                f"Image generation stopped at page {page.page_number} "
                                f"(no automatic retries). Budget: {get_package_image_budget(pkg)}"
                            )
                            break
        finally:
            snap = get_package_image_budget(pkg)
            if snap:
                warnings.append(
                    f"Package image budget usage: {snap.get('attempts', 0)}/"
                    f"{snap.get('max_attempts', 0)} attempts "
                    f"(quality={snap.get('quality', '')})."
                )

        # Local 300-DPI print prep (0 paid calls) once source PNGs exist.
        if any(p.image_path and os.path.isfile(p.image_path) for p in pages):
            try:
                prepared = _prepare_interior_print_assets(img_dir, pages)
                if prepared:
                    warnings.append(
                        f"Prepared {len(prepared)} interior(s) at 2250×3000 / 300 DPI locally."
                    )
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"300-DPI print prep warning: {type(exc).__name__}: {exc}")

    # ── Quality gate ────────────────────────────────────────────────
    # Validate only; never auto-regenerate paid images (Save/Export/preview safe).
    quality_result: dict | None = None
    if (
        pages
        and not ai_failed
        and quality_mode != "basic_test"
        and stage == "full"
        and any(p.image_path and os.path.isfile(p.image_path) for p in pages)
    ):
        page_dicts = [p.as_dict() for p in pages if p.image_path]
        qc_result = validate_coloring_book_pages(
            pages=page_dicts,
            main_character=main_character,
            setting=setting,
            topic_field=topic,
            regenerate=False,
            regenerate_fn=None,
        )
        for qr in qc_result.pages:
            if qr.image_path:
                matching = [p for p in pages if p.page_number == qr.page_number]
                if matching:
                    matching[0].image_path = qr.image_path
        quality_result = qc_result.as_dict()

        failed_pages = [qr for qr in quality_result.get("pages", []) if not qr.get("quality_pass")]
        if failed_pages:
            titles = [f"P{qr['page_number']} ({qr.get('topic','')})" for qr in failed_pages]
            warnings.append(f"Quality issues on {len(failed_pages)} page(s): {', '.join(titles)}")

    if image_failures:
        if quality_mode == "ai_image_coloring_page":
            from services.ebook_package import get_last_image_error
            real_error = get_last_image_error()
            if real_error:
                warnings.append(
                    f"[AI IMAGE COLORING PAGE] Image generation failed for {len(image_failures)} page(s): {real_error}"
                )
            else:
                warnings.append(
                    f"[AI IMAGE COLORING PAGE] Image generation failed for {len(image_failures)} page(s). "
                    "AI Image Coloring Page requires AI image generation. "
                    "Add AI_INTEGRATIONS_OPENAI_API_KEY and AI_INTEGRATIONS_OPENAI_BASE_URL to your .env file. "
                    "Or switch to Basic Test Fallback for a non-sellable test page."
                )

    return ColoringBookResult(
        product_title=title,
        subtitle=subtitle,
        pages=pages,
        cover_prompt=cover_prompt_final or build_cover_image_prompt(bible=bible, cover=cover_copy),
        image_failures=image_failures,
        warnings=warnings,
        quality_result=quality_result,
        generation_stage=stage,
        character_bible=bible.as_dict(),
        reference_image_path=ref_path,
        consistency_notes=consistency_notes,
    )
