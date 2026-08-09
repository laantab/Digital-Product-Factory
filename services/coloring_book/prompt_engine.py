"""Coloring Book prompt engine - character bible, story scenes, style constraints.

Builds authoritative interior/cover prompts from the user's full theme.
Does not call OpenAI, Tavily, or image APIs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Locked character / robber / composition blocks (verbatim on every page)
# ---------------------------------------------------------------------------

PRODUCT_STYLE_INTERIOR = (
    "PRODUCT STYLE: realistic American comic-book black-and-white line art for a "
    "professional superhero coloring book. Adult body proportions, clean bold outlines, "
    "consistent line weight, large open coloring areas, pure white page background."
)

PRODUCT_STYLE_COVER = (
    "PRODUCT STYLE: FULL-COLOR mass-market retail coloring-book COVER illustration "
    "(American comic-book packaging energy). Saturated primary colors, bold clean outlines, "
    "smooth cel shading, neon rim light, glossy print finish. Night city atmosphere with "
    "glowing windows and dramatic lens-flare glow behind the hero. Dynamic high-energy "
    "action composition filling the frame — hero dominant and larger than life. "
    "Upper ~20% kept relatively clear/dark for a retail title banner overlay by layout code."
)

THUNDER_VOLT_CHARACTER_LOCK = (
    "THUNDER VOLT CHARACTER LOCK (identical on every page and the cover; do not redefine):\n"
    "- Original Black male superhero named Thunder Volt\n"
    "- Adult, approximately 30-35 years old\n"
    "- Tall, muscular, athletic build\n"
    "- Deep-brown skin\n"
    "- Short, neatly shaped black hair\n"
    "- Neatly trimmed short beard and mustache\n"
    "- Strong jawline\n"
    "- Focused but reassuring expression\n"
    "- Blue fitted superhero suit (no armor, no mask, no helmet)\n"
    "- Exactly one large yellow lightning-bolt emblem centered on his chest\n"
    "- Yellow belt, yellow gloves, and yellow knee-high boots\n"
    "- Long solid yellow cape attached at both shoulders (never blue, never missing)\n"
    "- No costume color or design changes between pages or on the cover\n"
    "- No additional lightning emblems\n"
    "- No resemblance to any existing copyrighted superhero"
)

# Locked factory standard for sellable coloring-book covers (all future covers).
RETAIL_COVER_QUALITY_LOCK = (
    "RETAIL COVER QUALITY LOCK (factory standard — do not weaken):\n"
    "- Mass-market retail jumbo coloring-book cover energy (glossy comic packaging)\n"
    "- Night city atmosphere with glowing windows and neon cyan/yellow rim light\n"
    "- Dynamic high-energy action pose (leap/land/swing energy — never stiff arms-out stance)\n"
    "- Hero dominant and larger than life; supporting figures smaller but fully visible\n"
    "- Saturated primary colors, bold clean outlines, smooth cel shading\n"
    "- Upper ~20% kept relatively clear/dark for retail title banner overlay by layout code\n"
    "- No readable text/signs/labels/logos anywhere in the artwork (layout adds all typography)\n"
    "- No Marvel, Spider-Man, Bendon, or other copyrighted branding/characters"
)

ROBBER_ONE_LOCK = (
    "ROBBER ONE LOCK (identical whenever robbers appear; do not redefine):\n"
    "- Tall, slim adult man\n"
    "- Narrow face\n"
    "- Dark knit cap\n"
    "- Dark eye mask\n"
    "- Striped long-sleeve shirt\n"
    "- Plain pants\n"
    "- Carries one money bag only when the scene requires it"
)

ROBBER_TWO_LOCK = (
    "ROBBER TWO LOCK (identical whenever robbers appear; do not redefine):\n"
    "- Shorter, stockier adult man\n"
    "- Round face\n"
    "- Different knit cap from Robber One\n"
    "- Dark eye mask\n"
    "- Plain jacket over a light shirt\n"
    "- Plain pants\n"
    "- Carries one money bag only when the scene requires it"
)

# Bank-rescue only — never apply to farm/kids/generic themes.
COMPOSITION_REQUIREMENTS = (
    "COMPOSITION AND COLORING SPACE:\n"
    "- One clear primary action; Thunder Volt is the visual focal point\n"
    "- Full-page portrait composition with large subjects\n"
    "- Large open coloring regions; minimal crosshatching\n"
    "- No heavy shadows or gray fills\n"
    "- If the theme/setting is New York City: show a clearly readable NYC background cue "
    "(skyline with Empire State Building silhouette and/or classic NYC street + bank exterior)\n"
    "- Simplified background — recognizable place cues without filling every gap with detail\n"
    "- No tiny crowds; no cluttered signage; no dense architectural fill\n"
    "- No more than three foreground characters unless this is the police-arrival scene\n"
    "- Show FULL bodies of Thunder Volt and both robbers when they appear: complete heads, "
    "torsos, arms, legs, and feet inside the frame — never crop a robber to a partial body\n"
    "- Both robbers must be fully visible and clearly distinguishable at the same time\n"
    "- No malformed anatomy"
)

NEGATIVE_CONSTRAINTS = (
    "NEGATIVE CONSTRAINTS (must obey):\n"
    "- Exactly two robbers in every active robbery scene — never one, never three\n"
    "- No third robber; no additional masked person; no duplicate robber\n"
    "- No crowd of criminals; no extra money bags unless the scene requires them\n"
    "- Do not turn police, bank employees, or pedestrians into masked robbers\n"
    "- Police and bystanders only when the scene requires them; they must be unmasked\n"
    "- No guns, gore, blood, or firearms\n"
    "- No text, letters, numbers, logos, watermarks, speech bubbles, or captions in the art\n"
    "- No bank signs, street signs, storefront lettering, dollar-sign labels, or readable plaques\n"
    "- No color/gray/shading/gradients on interior pages; no solid-black costume fills\n"
    "- Scene instructions may change only action, camera angle, pose, simplified background, "
    "and whether police/bank employees appear — never redefine Thunder Volt or robber identity/costume"
)

GENERIC_COMPOSITION_REQUIREMENTS = (
    "COMPOSITION AND COLORING SPACE:\n"
    "- One clear primary subject matching the user's theme\n"
    "- Full-page portrait composition with large subjects\n"
    "- Large open coloring regions; minimal crosshatching\n"
    "- No heavy shadows or gray fills\n"
    "- Simplified background that matches the theme setting\n"
    "- No tiny crowds; no cluttered signage; no dense fill\n"
    "- Keep heads, hands, feet, and bodies inside the frame\n"
    "- No malformed anatomy"
)

GENERIC_NEGATIVE_CONSTRAINTS = (
    "NEGATIVE CONSTRAINTS (must obey):\n"
    "- Follow the user's theme only — do not invent unrelated stories\n"
    "- No superheroes, bank robbers, bandits, villains, guns, or crime scenes "
    "unless the user theme explicitly asks for them\n"
    "- No Thunder Volt, Marvel, DC, or other copyrighted characters\n"
    "- No guns, gore, blood, or firearms\n"
    "- No text, letters, numbers, logos, watermarks, speech bubbles, or captions in the art\n"
    "- No color/gray/shading/gradients on interior pages\n"
    "- Do not replace the user's requested characters or setting"
)

PRODUCT_STYLE_COVER_GENERIC = (
    "PRODUCT STYLE: FULL-COLOR mass-market retail coloring-book COVER illustration. "
    "Bright, friendly, high-quality packaging art with bold clean outlines and saturated color. "
    "Composition must literally show the user's requested cover scene. "
    "Upper ~20% kept relatively clear for a retail title banner overlay by layout code."
)

GENERIC_RETAIL_COVER_LOCK = (
    "RETAIL COVER QUALITY LOCK (theme-faithful factory standard):\n"
    "- Mass-market retail jumbo coloring-book cover energy\n"
    "- Illustrate the USER THEME literally as the cover scene\n"
    "- Friendly, inviting, age-appropriate for the theme\n"
    "- Saturated colors, bold clean outlines, smooth cel shading\n"
    "- Upper ~20% kept relatively clear for retail title banner overlay\n"
    "- No readable text/signs/logos in the artwork\n"
    "- No superheroes, bank robbers, or unrelated characters unless the theme asks for them"
)

# Legacy names used by image negative_prompt kwargs
INTERIOR_LINE_ART_CONSTRAINTS = (
    f"{PRODUCT_STYLE_INTERIOR} {COMPOSITION_REQUIREMENTS} {NEGATIVE_CONSTRAINTS}"
)

COVER_COLOR_CONSTRAINTS = (
    f"{PRODUCT_STYLE_COVER} Keep upper banner zone relatively clear for title overlay. "
    "NO readable text in the artwork. Original character only."
)

COLORING_NEGATIVE_PROMPT = (
    "gray, grayscale, grey, light gray, blush marks, blush shading, "
    "filled blush, shaded cheeks, cheek blush, any gray tone, any mid-tone, "
    "shading, shadow marks, filled shadows, gradient shading, texture, "
    "cross-hatching, hatching, stippling, grain, noise, "
    "color, coloured, realistic photograph, photo-realistic, photograph, "
    "border, frame, decorative border, margin outline, page outline, "
    "text, letters, numbers, watermark, logo, caption, label, speech bubble, "
    "messy lines, sketchy lines, rough draft, scribbles, "
    "dark background, black background, clutter, tiny details, tiny crowds, "
    "solid black costume fill, guns, firearms, gore, blood, child hero, "
    "third robber, three robbers, crowd of criminals, extra masked person, "
    "copyrighted character, marvel, dc comics, batman, spiderman, armor, mask on hero, helmet"
)

COVER_NEGATIVE_PROMPT = (
    "text, letters, title lettering, watermark, logo, speech bubble, "
    "bank sign, street sign, wall street sign, dollar sign on bag, storefront lettering, "
    "blank page, tiny icon only, lightning bolt alone as whole design, "
    "black and white line art, coloring book page, empty upper banner with nothing below, "
    "flat daytime lighting, dull matte colors, static standing pose, stiff arms-out stance, "
    "blue cape, missing cape, gray cape, costume color drift, "
    "copyrighted character, marvel, dc comics, spider-man, bendon, child hero, guns, gore, "
    "third robber, three robbers, crowd of criminals"
)

# Whether reference-image conditioning is available via our image wrapper.
# OpenAI gpt-image generate path does not accept a character reference image;
# optional images.edit may be attempted when a cover path is provided, but is
# not guaranteed. Prompt locks + preview approval remain the reliable path.
SUPPORTS_REFERENCE_IMAGE_CONDITIONING = False
SUPPORTS_IMAGE_SEED = False
SUPPORTS_IMAGE_TO_IMAGE = False  # attempted best-effort via images.edit; not guaranteed


# Canonical 12-scene bank-rescue sequence (unique camera / pose each page)
BANK_RESCUE_SCENES: list[dict[str, str]] = [
    {
        "id": "alarm_skyline",
        "topic": "Bank Alarm Over the New York Skyline",
        "includes_robbers": True,
        "includes_police": False,
        "max_foreground": 3,
        "beat": (
            "Establishing shot: simplified New York skyline and a bank entrance with an alarm "
            "strobe. Thunder Volt approaches in the air. Exactly two robbers (Robber One and "
            "Robber Two) are visible at the bank doors. Sparse background; large open spaces."
        ),
    },
    {
        "id": "robbers_exit",
        "topic": "Two Robbers Leave the Bank",
        "includes_robbers": True,
        "includes_police": False,
        "max_foreground": 3,
        "beat": (
            "Low-angle street shot: exactly two robbers burst from simplified bank doors onto "
            "a mostly empty sidewalk. Robber One carries one money bag. Thunder Volt appears "
            "above. No crowd; no third robber."
        ),
    },
    {
        "id": "hero_lands",
        "topic": "Thunder Volt Lands on the Street",
        "includes_robbers": True,
        "includes_police": False,
        "max_foreground": 3,
        "beat": (
            "Three-quarter hero landing: Thunder Volt touches down as the clear focal point. "
            "Exactly two robbers react in mid-distance. Simplified skyscraper silhouettes; "
            "large open coloring regions; no tiny crowd."
        ),
    },
    {
        "id": "blocks_getaway",
        "topic": "Thunder Volt Blocks the Getaway",
        "includes_robbers": True,
        "includes_police": False,
        "max_foreground": 3,
        "beat": (
            "Confrontational mid-shot: Thunder Volt blocks the path with one palm raised and "
            "simple lightning arcs. Exactly two robbers skid to a halt. Minimal street detail."
        ),
    },
    {
        "id": "escape_to_car",
        "topic": "Robbers Race Toward the Getaway Car",
        "includes_robbers": True,
        "includes_police": False,
        "max_foreground": 3,
        "beat": (
            "Side action shot: exactly two robbers sprint toward one getaway car. Thunder Volt "
            "pursues. Simplified curb and building outlines only; no taxi clutter; no crowds."
        ),
    },
    {
        "id": "lightning_disables_car",
        "topic": "Lightning Disables the Getaway Car",
        "includes_robbers": True,
        "includes_police": False,
        "max_foreground": 3,
        "beat": (
            "Diagonal action shot: Thunder Volt (focal point) sends controlled lightning into "
            "the car engine bay. Exactly two robbers recoil. No fire, no guns, sparse background."
        ),
    },
    {
        "id": "shields_pedestrians",
        "topic": "Thunder Volt Shields Pedestrians",
        "includes_robbers": True,
        "includes_police": False,
        "max_foreground": 3,
        "beat": (
            "Protective pose: Thunder Volt creates a simple energy shield for one or two "
            "unmasked pedestrians. Exactly two robbers stay outside the shield in mid-ground. "
            "No crowd; simplified bank/street background."
        ),
    },
    {
        "id": "removes_bag",
        "topic": "Thunder Volt Takes the Money Bag",
        "includes_robbers": True,
        "includes_police": False,
        "max_foreground": 3,
        "beat": (
            "Close mid-shot: Thunder Volt firmly takes the single money bag from Robber One. "
            "Robber Two stands nearby shocked. Exactly two robbers total. Sparse background."
        ),
    },
    {
        "id": "stops_second_robber",
        "topic": "Thunder Volt Stops the Second Robber",
        "includes_robbers": True,
        "includes_police": False,
        "max_foreground": 3,
        "beat": (
            "Dynamic capture pose: Thunder Volt restrains Robber Two with a non-lethal lightning "
            "hold. Robber One is visible nearby, already subdued. Exactly two robbers; no third."
        ),
    },
    {
        "id": "police_arrive",
        "topic": "Police Arrive on the Scene",
        "includes_robbers": True,
        "includes_police": True,
        "max_foreground": 5,
        "beat": (
            "Police-arrival scene: one or two clearly unmasked officers approach. Thunder Volt "
            "stands with the money bag over exactly two subdued robbers. Officers are not masked "
            "and must not look like robbers. Simplified street; no crowd of criminals."
        ),
    },
    {
        "id": "returns_money",
        "topic": "Thunder Volt Returns the Money",
        "includes_robbers": True,
        "includes_police": False,
        "max_foreground": 3,
        "beat": (
            "Warm handoff: Thunder Volt returns one money bag to one unmasked bank employee at "
            "a simplified bank entrance. Exactly two robbers remain secured in the background. "
            "No cluttered signage or lettering in the image."
        ),
    },
    {
        "id": "heroic_finale",
        "topic": "Thunder Volt Heroic Finale",
        "includes_robbers": True,
        "includes_police": False,
        "max_foreground": 3,
        "beat": (
            "Heroic finale: Thunder Volt stands on a rooftop overlooking a simplified New York "
            "skyline. Exactly two bound robbers sit behind him. Large open sky for coloring; "
            "triumphant focal pose; no text in the art."
        ),
    },
]


@dataclass
class CharacterBible:
    hero_name: str
    hero_identity: str
    hero_description: str
    robber_a: str
    robber_b: str
    location: str
    story_summary: str
    product_kind: str = "superhero coloring book"
    is_bank_rescue: bool = False
    full_theme: str = ""

    def as_prompt_block(self) -> str:
        """Authoritative locked bible block reused unchanged across pages."""
        if self.is_bank_rescue:
            return (
                "CHARACTER BIBLE (must match exactly on every page and the cover):\n"
                f"{THUNDER_VOLT_CHARACTER_LOCK}\n"
                f"{ROBBER_ONE_LOCK}\n"
                f"{ROBBER_TWO_LOCK}\n"
                f"- Location: {self.location}\n"
                f"- Story: {self.story_summary}\n"
                f"- Full user theme: {self.full_theme}\n"
            )
        if is_farm_theme(self.full_theme) or self.product_kind == "farm animal coloring book":
            return (
                "FARM BOOK BIBLE (cover vs interiors — follow carefully):\n"
                f"- COVER ONLY (not interior pages): friendly farmer on a porch waving, "
                f"friendly dog by his side.\n"
                "- INTERIOR PAGES: each page is ONE individual farm animal or farm-object scene.\n"
                "- Do NOT put the farmer, the dog, or the porch on interior pages.\n"
                "- Do NOT repeat the cover composition on interior pages.\n"
                f"- Setting for interiors: {self.location} (simple barn/field cues only).\n"
                f"- Book theme summary: {self.story_summary}\n"
                "- Cute friendly Bold & Easy coloring style; large open coloring spaces.\n"
                "- No superheroes, robbers, bandits, or crime.\n"
            )
        return (
            "CHARACTER / THEME BIBLE (must match the user's request on every page and the cover):\n"
            f"- Main subject: {self.hero_name} — {self.hero_identity}. {self.hero_description}\n"
            f"- Setting: {self.location}\n"
            f"- Story/theme: {self.story_summary}\n"
            f"- Full user theme (do not shorten or replace): {self.full_theme}\n"
            "- Keep characters consistent across pages.\n"
            "- Do not invent superheroes, bank robbers, bandits, or crime scenes "
            "unless the user theme explicitly asks for them.\n"
            "- Original characters only — no copyrighted heroes.\n"
        )

    def as_compact_bible(self) -> str:
        """Same locked text used for image APIs — never a shortened rewrite of identity."""
        return self.as_prompt_block().strip()

    def as_dict(self) -> dict:
        return {
            "hero_name": self.hero_name,
            "hero_identity": self.hero_identity,
            "hero_description": self.hero_description,
            "robber_a": self.robber_a,
            "robber_b": self.robber_b,
            "location": self.location,
            "story_summary": self.story_summary,
            "product_kind": self.product_kind,
            "is_bank_rescue": self.is_bank_rescue,
            "full_theme": self.full_theme,
            "character_lock": THUNDER_VOLT_CHARACTER_LOCK if self.is_bank_rescue else "",
            "supports_reference_image": SUPPORTS_REFERENCE_IMAGE_CONDITIONING,
        }


@dataclass
class CoverCopy:
    title: str
    subtitle: str
    badge: str = "Jumbo Coloring & Activity Book"
    overlay_style: str = "retail_jumbo_banner"


def _normalize_theme(theme: str) -> str:
    return re.sub(r"\s+", " ", str(theme or "").strip())


def is_farm_theme(theme: str) -> bool:
    t = (theme or "").lower()
    return any(
        k in t
        for k in (
            "farm", "farmer", "barn", "porch", "pasture", "tractor", "livestock",
            "cow", "pig", "chicken", "rooster", "sheep", "goat", "horse", "duck",
            "hen", "chick", "barnyard", "homestead", "ranch",
        )
    )


def is_superhero_narrative(theme: str, main_character: str = "", art_style: str = "") -> bool:
    """True only for explicit superhero / bank-rescue stories — never from art style alone."""
    blob = f"{theme} {main_character}".lower()
    if is_farm_theme(blob):
        return False
    # Art style must NOT decide product story (comic ≠ superhero).
    _ = art_style
    strong = (
        "superhero", "thunder volt", "supervillain", "bank robber", "robbing a bank",
        "lightning bolt emblem", "cape and boots",
    )
    if any(s in blob for s in strong):
        return True
    # Weak "hero" alone is not enough (blocks friendly farm/kids themes).
    return ("super hero" in blob) or ("super-hero" in blob)


def is_bank_rescue_theme(theme: str) -> bool:
    """Strict: only true bank-robbery / Thunder Volt rescue stories."""
    t = (theme or "").lower()
    if is_farm_theme(t):
        return False
    if "thunder volt" in t and ("bank" in t or "robber" in t or "robbing" in t):
        return True
    if "superhero" in t and ("bank" in t or "robber" in t or "robbing" in t):
        return True
    if "new york" in t and ("robber" in t or "robbing" in t) and ("bank" in t or "superhero" in t):
        return True
    return False


def uses_comic_line_art(theme: str, art_style: str = "", main_character: str = "") -> bool:
    """Comic-book line art when requested by style or true superhero narrative."""
    style = (art_style or "").lower()
    if "kawaii" in style and not is_superhero_narrative(theme, main_character, art_style):
        return False
    if any(k in style for k in ("comic", "realistic", "bold kdp")):
        return True
    return is_superhero_narrative(theme, main_character, art_style)


def extract_hero_name(theme: str, main_character: str = "") -> str:
    if main_character and str(main_character).strip():
        return str(main_character).strip()
    theme = _normalize_theme(theme)
    t_low = theme.lower()
    if is_farm_theme(t_low) and "farmer" in t_low:
        return "Farmer"
    if "thunder volt" in t_low or (is_bank_rescue_theme(theme) and "volt" in t_low):
        return "Thunder Volt"
    named = re.search(
        r"\b(?:named|called|known as)\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,3})",
        theme,
    )
    if named:
        return named.group(1).strip()
    lead = re.match(
        r"^([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,2})\s+is\b",
        theme,
    )
    if lead:
        return lead.group(1).strip()
    # Only treat ALL-CAPS pairs as names for known superhero themes.
    if is_superhero_narrative(theme):
        caps = re.search(r"\b([A-Z]{2,})\s+([A-Z]{2,})\b", theme)
        if caps:
            return f"{caps.group(1).title()} {caps.group(2).title()}"
    # Friendly noun fallback from theme words
    for noun in ("farmer", "girl", "boy", "child", "dog", "cat", "unicorn", "dragon"):
        if noun in t_low:
            return noun.title()
    short = theme.split(".")[0].strip()
    if 3 <= len(short) <= 48 and "robber" not in short.lower():
        return short
    return "Main Character"


def build_character_bible(
    theme: str,
    *,
    main_character: str = "",
    setting: str = "",
) -> CharacterBible:
    theme_n = _normalize_theme(theme)
    hero = extract_hero_name(theme_n, main_character)
    t_low = theme_n.lower()
    bank_rescue = is_bank_rescue_theme(theme_n)
    farm = is_farm_theme(theme_n)

    location = setting.strip() if setting else ""
    if not location:
        if "new york" in t_low and bank_rescue:
            location = "New York City"
        elif farm:
            location = "a friendly farm"
        else:
            loc_m = re.search(
                r"\b(?:in|at|on|inside|around|near)\s+"
                r"([A-Za-z][A-Za-z]+(?:\s+[A-Za-z][A-Za-z]+){0,3})",
                theme_n,
            )
            location = loc_m.group(1).strip() if loc_m else "the theme setting"

    if bank_rescue:
        # Locked identity — scene prompts must never redefine these strings.
        if hero.lower() != "thunder volt" and "thunder volt" in t_low:
            hero = "Thunder Volt"
        hero_identity = "Black male adult superhero"
        hero_description = (
            "Adult 30-35, tall muscular athletic build, deep-brown skin, short neatly shaped "
            "black hair, neatly trimmed short beard and mustache, strong jawline, focused but "
            "reassuring expression, fitted blue suit with one yellow chest lightning emblem, "
            "yellow belt, yellow gloves, yellow knee-high boots, long solid yellow cape at both "
            "shoulders, no mask, no helmet, no armor."
        )
        robber_a = (
            "Robber One: taller slim adult man, narrow face, dark knit cap, dark eye mask, "
            "striped long-sleeve shirt, plain pants"
        )
        robber_b = (
            "Robber Two: shorter heavier stockier adult man, round face, different knit cap, "
            "dark eye mask, plain jacket over light shirt, plain pants"
        )
        story = (
            f"{hero} is stopping two men from robbing a bank in {location}. "
            "Exactly two robbers — never three. No guns, no gore."
        )
        product_kind = "superhero coloring book"
    elif farm:
        hero = "Farm Animals"
        hero_identity = "individual farm animals (interior pages)"
        hero_description = (
            "COVER ONLY: a friendly adult farmer waving on a porch with a friendly dog. "
            "INTERIOR PAGES: one farm animal or farm object per page — never the farmer, "
            "never the dog, never the porch cover scene."
        )
        robber_a = ""
        robber_b = ""
        story = (
            "Cover shows a farmer on the porch waving with a dog; "
            "interior pages are individual farm animal scenes only."
        )
        product_kind = "farm animal coloring book"
        location = location if location != "the theme setting" else "a friendly farm"
    else:
        if "black" in t_low and "superhero" in t_low:
            hero_identity = "Black male adult superhero"
            hero_description = (
                f"{hero} is a confident adult superhero with a consistent face and costume."
            )
            product_kind = "superhero coloring book"
        elif is_superhero_narrative(theme_n, main_character):
            hero_identity = "adult superhero"
            hero_description = (
                f"{hero} is a confident adult superhero with a consistent face and costume."
            )
            product_kind = "superhero coloring book"
        else:
            hero_identity = "theme main character"
            hero_description = (
                f"{hero} matches the user's theme and stays consistent on every page."
            )
            product_kind = "coloring book"
        robber_a = ""
        robber_b = ""
        story = theme_n

    return CharacterBible(
        hero_name=hero,
        hero_identity=hero_identity,
        hero_description=hero_description,
        robber_a=robber_a,
        robber_b=robber_b,
        location=location,
        story_summary=story,
        product_kind=product_kind,
        is_bank_rescue=bank_rescue,
        full_theme=theme_n,
    )


def derive_cover_copy(theme: str, *, product_title: str = "", subtitle: str = "") -> CoverCopy:
    bible = build_character_bible(theme)
    title = (product_title or "").strip()
    if not title or len(title) > 48 or title.lower() == theme.lower():
        if bible.is_bank_rescue:
            title = "THUNDER VOLT"
        elif is_farm_theme(theme):
            title = "FARM FRIENDS"
        else:
            title = (bible.hero_name or "COLORING BOOK").upper()[:48]
    else:
        if " is " in title.lower() or len(title) > 40:
            title = (bible.hero_name or title[:40]).upper()
        elif title.lower() == bible.hero_name.lower():
            title = bible.hero_name.upper()

    sub = (subtitle or "").strip()
    if not sub:
        if bible.is_bank_rescue:
            sub = "New York Bank Rescue" if "new york" in theme.lower() else "Bank Rescue"
        elif is_farm_theme(theme):
            sub = "Barnyard Coloring Fun"
        else:
            sub = "Coloring & Activity Fun"

    badge = "Jumbo Coloring & Activity Book"
    return CoverCopy(
        title=title,
        subtitle=sub,
        badge=badge,
        overlay_style="retail_jumbo_banner",
    )


def _farm_story_scenes() -> list[dict[str, str]]:
    """Interior pages only — one animal/object each; cover cast stays off-page."""
    solo = (
        "Show ONLY this subject as the large main focus. "
        "Do NOT include the farmer, the dog, the porch, or any people. "
        "Simple farm background only (fence/barn/field cues). Large open coloring spaces."
    )
    pairs = [
        ("Cow in the Pasture", f"One friendly cow standing in a grassy pasture. {solo}"),
        ("Pig in the Mud Puddle", f"One happy pig playing in a shallow mud puddle. {solo}"),
        ("Hen and Chicks", f"One mother hen with a few fluffy chicks. {solo}"),
        ("Horse in the Barn", f"One gentle horse looking out from a barn stall. {solo}"),
        ("Sheep in the Meadow", f"One or two fluffy sheep grazing in a meadow. {solo}"),
        ("Goat by the Fence", f"One curious goat beside a wooden fence. {solo}"),
        ("Ducks at the Pond", f"Two or three ducks at a small farm pond. {solo}"),
        ("Tractor in the Field", f"One farm tractor parked in a field. {solo}"),
        ("Barn Cat on Hay", f"One friendly barn cat resting on a hay bale. {solo}"),
        ("Rooster on a Post", f"One proud rooster on a fence post. {solo}"),
        ("Pony in the Paddock", f"One gentle pony in a small paddock. {solo}"),
        ("Veggie Garden Patch", f"A simple vegetable garden with large veggies (no people). {solo}"),
    ]
    return [
        {
            "id": f"farm{i}",
            "topic": topic,
            "beat": beat,
            "includes_robbers": False,
            "includes_police": False,
            "max_foreground": 2,
        }
        for i, (topic, beat) in enumerate(pairs, start=1)
    ]


def story_scenes_for_theme(theme: str, page_count: int, bible: CharacterBible | None = None) -> list[dict[str, str]]:
    bible = bible or build_character_bible(theme)
    if bible.is_bank_rescue or is_bank_rescue_theme(theme):
        scenes = list(BANK_RESCUE_SCENES)
    elif is_farm_theme(theme):
        scenes = _farm_story_scenes()
    else:
        # Theme-faithful generic beats — no robbers, no Thunder Volt.
        subject = bible.hero_name
        loc = bible.location
        theme_short = (bible.full_theme or theme)[:120]
        scenes = [
            {
                "id": f"g{i}",
                "topic": topic,
                "beat": beat,
                "includes_robbers": False,
                "includes_police": False,
                "max_foreground": 3,
            }
            for i, (topic, beat) in enumerate(
                [
                    (f"{subject} Welcome Scene", f"Friendly establishing scene of {subject} in {loc}, matching: {theme_short}"),
                    (f"{subject} Everyday Moment", f"A calm everyday moment with {subject} in {loc}."),
                    (f"{subject} With a Friend", f"{subject} with a friendly companion matching the theme."),
                    (f"{subject} Exploring", f"{subject} exploring an interesting part of {loc}."),
                    (f"{subject} Helping Out", f"{subject} helping with a kind theme-appropriate task."),
                    (f"{subject} Playful Scene", f"A playful, cheerful scene featuring {subject}."),
                    (f"{subject} Quiet Moment", f"A quiet cozy moment with {subject} in {loc}."),
                    (f"{subject} Big Adventure", f"A light adventure moment still matching the friendly theme."),
                    (f"{subject} Favorite Place", f"{subject} in a favorite place within {loc}."),
                    (f"{subject} With Animals or Props", f"{subject} with theme-appropriate animals or props."),
                    (f"{subject} Celebration", f"A happy celebration or achievement moment for {subject}."),
                    (f"{subject} Finale Portrait", f"Warm finale portrait of {subject} in {loc}."),
                ],
                start=1,
            )
        ]

    if page_count <= 0:
        return []
    if len(scenes) >= page_count:
        return scenes[:page_count]
    out = list(scenes)
    n = 1
    while len(out) < page_count:
        base = scenes[(len(out)) % len(scenes)]
        out.append(
            {
                **base,
                "id": f"{base['id']}_var{n}",
                "topic": f"{base['topic']} (Alternate Angle)",
                "beat": f"Alternate camera angle of the same story beat: {base['beat']}",
            }
        )
        n += 1
    return out


def build_interior_page_prompt(
    *,
    bible: CharacterBible,
    scene: dict[str, str],
    page_number: int,
    art_style: str = "",
    total_pages: int = 12,
) -> str:
    """Master prompt structure — locks first; only scene action may vary."""
    # Comic interior style only for bank-rescue; farm/generic stay Bold & Easy.
    if bible.is_bank_rescue:
        style_block = PRODUCT_STYLE_INTERIOR
    else:
        style_block = (
            "PRODUCT STYLE: Bold & Easy black-and-white coloring page — cute friendly shapes, "
            "bold clean outlines, large open coloring spaces, pure white background, "
            "no gray, no shading, no color, no text, no watermark."
        )

    topic = scene.get("topic", "Scene")
    beat = scene.get("beat", "")
    includes_robbers = bool(scene.get("includes_robbers", False)) and bible.is_bank_rescue
    includes_police = bool(scene.get("includes_police", False)) and bible.is_bank_rescue
    max_fg = int(scene.get("max_foreground") or (5 if includes_police else 3))

    farm = is_farm_theme(bible.full_theme) or bible.product_kind == "farm animal coloring book"

    if bible.is_bank_rescue:
        robber_clause = (
            "Show exactly Robber One and Robber Two as locked above — never a third robber."
            if includes_robbers
            else "Do not add robbers in this scene."
        )
        police_clause = (
            "Unmasked police may appear as required; they must not look like the two robbers."
            if includes_police
            else "No police officers in this scene."
        )
        identity_clause = (
            "Do not redefine Thunder Volt's face, hair, costume, cape, boots, or emblem."
        )
        composition = COMPOSITION_REQUIREMENTS
        negatives = NEGATIVE_CONSTRAINTS
        theme_line = f"THEME (do not shorten or replace): {bible.full_theme}"
    elif farm:
        robber_clause = "Do not add robbers, bandits, villains, crime, or weapons."
        police_clause = "No people in this interior scene."
        identity_clause = (
            "INTERIOR RULE: one animal/object scene only. "
            "Do NOT draw the farmer, the dog, the porch, or the cover scene."
        )
        composition = GENERIC_COMPOSITION_REQUIREMENTS
        negatives = (
            f"{GENERIC_NEGATIVE_CONSTRAINTS}\n"
            "- No farmer, no person, no dog mascot, no porch waving scene on this page\n"
            "- No repeating the cover illustration"
        )
        theme_line = (
            "INTERIOR THEME: individual farm animal coloring pages. "
            "Cover (separate page) already has the farmer-on-porch-with-dog scene — "
            "do not repeat it here."
        )
        max_fg = min(max_fg, 2)
    else:
        robber_clause = "Do not add robbers, bandits, villains, or crime."
        police_clause = "No police chase or crime scene."
        identity_clause = (
            "Stay faithful to the user theme; do not turn this into a superhero or bank robbery."
        )
        composition = GENERIC_COMPOSITION_REQUIREMENTS
        negatives = GENERIC_NEGATIVE_CONSTRAINTS
        theme_line = f"THEME (do not shorten or replace): {bible.full_theme}"

    return (
        f"{style_block}\n"
        f"{bible.as_prompt_block()}\n"
        f"UNIQUE SCENE ACTION (page {page_number} of {total_pages}) — {topic}:\n"
        f"{beat}\n"
        f"{robber_clause} {police_clause} "
        f"Max {max_fg} foreground subjects. Unique camera angle and pose for this page only. "
        f"{identity_clause}\n"
        f"{composition}\n"
        f"{negatives}\n"
        f"{theme_line}"
    )


def build_cover_image_prompt(*, bible: CharacterBible, cover: CoverCopy) -> str:
    """Cover follows the user theme; bank-rescue locks apply only to that product."""
    if bible.is_bank_rescue:
        loc = bible.location or "New York City"
        nyc_clause = (
            "Nighttime New York City: dark building silhouettes, glowing cyan/teal windows, "
            "neon rim light, bank street exterior readable, Empire State Building silhouette "
            "in the skyline — city must be obvious at a glance."
            if "new york" in loc.lower() or "new york" in (bible.full_theme or "").lower()
            else f"Nighttime setting must clearly indicate: {loc}."
        )
        return (
            f"{PRODUCT_STYLE_COVER}\n"
            f"{RETAIL_COVER_QUALITY_LOCK}\n"
            f"{bible.as_prompt_block()}\n"
            f"UNIQUE COVER ACTION: Retail jumbo coloring-book cover of {bible.hero_name} stopping "
            f"exactly two bank robbers. Hero is the dominant foreground figure in a DYNAMIC action "
            f"pose (leaping, landing, or mid-swing energy — not a stiff arms-out standing pose). "
            f"Bright yellow/cyan rim lighting makes the hero pop off the dark background. "
            f"Yellow cape must be clearly visible. "
            f"Show BOTH robbers in FULL BODY (head-to-feet) in the mid-ground — Robber One (taller, "
            f"striped shirt, knit cap) and Robber Two (shorter, stockier, jacket) fully visible and "
            f"not cropped. {nyc_clause} "
            f"Upper ~20% kept relatively clear/dark for a retail title banner overlay.\n"
            f"{COMPOSITION_REQUIREMENTS}\n"
            f"{NEGATIVE_CONSTRAINTS}\n"
            f"COVER EXTRA: do not paint any words, letters, numbers, logos, author names, watermarks, "
            f"bank signs, street signs, or dollar-sign labels in the art. "
            f"Not a tiny lightning bolt as the whole design. "
            f"Do not crop either robber. Do not hide city cues behind the hero. "
            f"Do not imitate Marvel, Spider-Man, Bendon, or any copyrighted hero/brand — "
            f"original Thunder Volt only. "
            f"Layout will add title '{cover.title}' / '{cover.subtitle}' / '{cover.badge}' later "
            f"with overlay_style={cover.overlay_style} — never paint the title or author into the artwork.\n"
            f"THEME (do not shorten or replace): {bible.full_theme}"
        )

    # Theme-faithful cover — literally illustrate the user's request.
    theme = bible.full_theme
    if is_farm_theme(theme):
        action = (
            "UNIQUE COVER ACTION: Friendly daytime farm cover showing a farmer standing on a "
            "farmhouse porch waving hello, with a friendly dog by his side. Warm sunshine, "
            "barn and fields in the soft background. Cheerful, inviting, kids-friendly. "
            "No robbers, no bandits, no superheroes, no crime."
        )
        if "porch" in theme.lower() or "wav" in theme.lower() or "dog" in theme.lower():
            action = (
                f"UNIQUE COVER ACTION: Literally illustrate this cover scene from the user theme: "
                f"\"{theme}\". Dominant friendly farmer on the porch waving, friendly dog beside him, "
                f"bright daytime farm atmosphere. No robbers, no bandits, no superheroes, no crime."
            )
    else:
        action = (
            f"UNIQUE COVER ACTION: Literally illustrate the user's theme as the cover scene: "
            f"\"{theme}\". Main subject is {bible.hero_name} in {bible.location}. "
            f"Friendly, inviting retail coloring-book energy. "
            f"Do not invent bank robbers, bandits, or superheroes unless the theme asks for them."
        )

    return (
        f"{PRODUCT_STYLE_COVER_GENERIC}\n"
        f"{GENERIC_RETAIL_COVER_LOCK}\n"
        f"{bible.as_prompt_block()}\n"
        f"{action} "
        f"Upper ~20% kept relatively clear for a retail title banner overlay.\n"
        f"{GENERIC_COMPOSITION_REQUIREMENTS}\n"
        f"{GENERIC_NEGATIVE_CONSTRAINTS}\n"
        f"COVER EXTRA: do not paint any words, letters, numbers, logos, or watermarks in the art. "
        f"Layout will add title '{cover.title}' / '{cover.subtitle}' / '{cover.badge}' later "
        f"with overlay_style={cover.overlay_style} — never paint the title into the artwork.\n"
        f"THEME (do not shorten or replace): {theme}"
    )


def build_local_story_pages(
    theme: str,
    page_count: int,
    *,
    main_character: str = "",
    setting: str = "",
    art_style: str = "",
    include_captions: bool = False,
) -> tuple[list[dict], str, CharacterBible, CoverCopy]:
    """Deterministic page plan + cover prompt. No AI calls."""
    bible = build_character_bible(theme, main_character=main_character, setting=setting)
    cover = derive_cover_copy(theme, product_title="", subtitle="")
    scenes = story_scenes_for_theme(theme, page_count, bible)
    pages = []
    for i, scene in enumerate(scenes):
        pages.append(
            {
                "topic": scene["topic"],
                "line_art_prompt": build_interior_page_prompt(
                    bible=bible,
                    scene=scene,
                    page_number=i + 1,
                    art_style=art_style,
                    total_pages=page_count,
                ),
                "caption": scene["topic"] if include_captions else "",
                "scene_id": scene["id"],
                "includes_robbers": bool(scene.get("includes_robbers", False)) and bible.is_bank_rescue,
            }
        )
    cover_prompt = build_cover_image_prompt(bible=bible, cover=cover)
    return pages, cover_prompt, bible, cover


def inject_bible_into_prompt(prompt: str, bible: CharacterBible) -> str:
    """Ensure AI-returned prompts still contain the locked bible + full theme.

    Appends missing locks after the prompt so unique scene text stays intact, but
    for bank-rescue themes prefer rebuilding from locks when the lock text is absent.
    """
    prompt = str(prompt or "").strip()
    if bible.is_bank_rescue:
        if THUNDER_VOLT_CHARACTER_LOCK in prompt and ROBBER_ONE_LOCK in prompt and ROBBER_TWO_LOCK in prompt:
            if bible.full_theme and bible.full_theme.lower() not in prompt.lower():
                return prompt + f"\nTHEME (do not shorten or replace): {bible.full_theme}"
            return prompt
        # Missing locks — append authoritative locks (do not let scene redefine identity)
        extras = [THUNDER_VOLT_CHARACTER_LOCK, ROBBER_ONE_LOCK, ROBBER_TWO_LOCK, NEGATIVE_CONSTRAINTS]
        if bible.full_theme and bible.full_theme.lower() not in prompt.lower():
            extras.append(f"THEME (do not shorten or replace): {bible.full_theme}")
        return prompt + "\n" + "\n".join(extras)

    has_theme = bool(bible.full_theme) and bible.full_theme.lower() in prompt.lower()
    has_bible = "CHARACTER / THEME BIBLE" in prompt or "CHARACTER BIBLE" in prompt
    extras: list[str] = []
    if not has_bible:
        extras.append(bible.as_prompt_block())
    if not has_theme and bible.full_theme:
        extras.append(f"THEME (do not shorten or replace): {bible.full_theme}")
    # Strip accidental bank-rescue contamination from AI drafts on non-bank themes.
    if not bible.is_bank_rescue and ("robber" in prompt.lower() or "thunder volt" in prompt.lower()):
        extras.append(GENERIC_NEGATIVE_CONSTRAINTS)
    if extras:
        return prompt + "\n" + "\n".join(extras)
    return prompt


def finalize_interior_prompt(prompt: str, bible: CharacterBible, art_style: str = "") -> str:
    prompt = inject_bible_into_prompt(prompt, bible)
    if bible.is_bank_rescue:
        if uses_comic_line_art(bible.full_theme, art_style, bible.hero_name):
            if PRODUCT_STYLE_INTERIOR not in prompt and "American comic-book" not in prompt:
                prompt = (
                    f"{prompt}\n{PRODUCT_STYLE_INTERIOR}\n"
                    f"{COMPOSITION_REQUIREMENTS}\n{NEGATIVE_CONSTRAINTS}"
                )
    else:
        # Never append Thunder Volt / robber constraints to unrelated themes.
        if GENERIC_NEGATIVE_CONSTRAINTS not in prompt:
            prompt = f"{prompt}\n{GENERIC_COMPOSITION_REQUIREMENTS}\n{GENERIC_NEGATIVE_CONSTRAINTS}"
    return prompt


def pdf_metadata_for_theme(theme: str = "", *, product_title: str = "") -> dict[str, str]:
    """Canonical PDF document info for Thunder Volt / coloring books."""
    if is_bank_rescue_theme(theme) or "thunder volt" in (theme or "").lower() or (
        product_title or ""
    ).lower().startswith("thunder"):
        return {
            "title": "Thunder Volt Coloring Book",
            "author": "Digital Product Factory",
            "subject": "Thunder Volt stops two bank robbers in New York City",
            "keywords": (
                "Thunder Volt, Black superhero, New York City, bank robbery, "
                "superhero coloring book"
            ),
        }
    title = (product_title or "Coloring Book").strip() or "Coloring Book"
    return {
        "title": title,
        "author": "Digital Product Factory",
        "subject": (theme or title)[:200],
        "keywords": "coloring book",
    }


def validate_cover_prompt_lock(cover_prompt: str, theme: str = "") -> list[str]:
    """Validate cover prompt — bank-rescue lock OR theme-faithful generic lock."""
    issues: list[str] = []
    prompt = str(cover_prompt or "")
    low = prompt.lower()
    if not prompt.strip():
        return ["Cover prompt is empty"]

    bank = is_bank_rescue_theme(theme) or (
        THUNDER_VOLT_CHARACTER_LOCK in prompt and "bank robber" in low
    )

    if bank:
        if RETAIL_COVER_QUALITY_LOCK not in prompt:
            issues.append("Missing RETAIL COVER QUALITY LOCK")
        if PRODUCT_STYLE_COVER not in prompt:
            issues.append("Missing PRODUCT_STYLE_COVER retail style block")
        if "night" not in low:
            issues.append("Cover prompt must require night atmosphere")
        if "yellow cape" not in low:
            issues.append("Cover prompt must lock yellow cape")
        for lock in (THUNDER_VOLT_CHARACTER_LOCK, ROBBER_ONE_LOCK, ROBBER_TWO_LOCK):
            if lock not in prompt:
                issues.append("Cover prompt missing character/robber lock block")
                break
    else:
        # Theme-faithful products must NOT inherit Thunder Volt / robber LOCK blocks.
        # (Negative-constraint text may mention those words as things to avoid.)
        if THUNDER_VOLT_CHARACTER_LOCK in prompt or "THUNDER VOLT CHARACTER LOCK" in prompt:
            issues.append("Non-bank theme cover must not include Thunder Volt lock")
        if ROBBER_ONE_LOCK in prompt or "stopping exactly two bank robbers" in low:
            issues.append("Non-bank theme cover must not include bank-robber cover action")
        if GENERIC_RETAIL_COVER_LOCK not in prompt and "user theme" not in low:
            issues.append("Missing theme-faithful retail cover lock")
        if theme and theme.lower()[:40] not in low and theme.lower() not in low:
            # Allow paraphrased farm covers that still include key nouns.
            keys = [w for w in re.findall(r"[a-z]{4,}", theme.lower()) if w not in {"with", "that", "this", "from"}]
            if keys and not any(k in low for k in keys[:4]):
                issues.append("Cover prompt missing user theme content")
        if is_farm_theme(theme):
            if "stopping exactly two bank robbers" in low or "robber one" in low:
                issues.append("Farm cover must not include robber cover action")
            if "porch" not in low and "farmer" not in low and "dog" not in low:
                issues.append("Farm cover should feature farmer/porch/dog from the theme")

    if "title banner" not in low and "upper ~20%" not in low:
        issues.append("Cover prompt must reserve upper banner zone for layout title")
    if "do not paint any words" not in low and "never paint the title" not in low:
        issues.append("Cover prompt must forbid painted title/text in art")
    return issues


def validate_locked_prompts(pages: list[dict], theme: str) -> list[str]:
    """Return validation issues for locked prompt assembly (no API calls)."""
    issues: list[str] = []
    if not pages:
        return ["No pages to validate"]
    bible = build_character_bible(theme)
    locks = []
    if bible.is_bank_rescue:
        locks = [THUNDER_VOLT_CHARACTER_LOCK, ROBBER_ONE_LOCK, ROBBER_TWO_LOCK]
    first_lock = None
    for i, page in enumerate(pages):
        prompt = str(page.get("line_art_prompt") or page.get("prompt") or "")
        if bible.is_bank_rescue:
            for lock in locks:
                if lock not in prompt:
                    issues.append(f"Page {i+1}: missing locked block fragment")
            if "exactly two robbers" not in prompt.lower() and "Exactly two robbers" not in prompt:
                if "exactly Robber One and Robber Two" not in prompt:
                    issues.append(f"Page {i+1}: missing exactly-two-robbers requirement")
            if "third robber" not in prompt.lower():
                issues.append(f"Page {i+1}: missing third-robber prohibition")
            if "large open coloring" not in prompt.lower():
                issues.append(f"Page {i+1}: missing large open coloring requirement")
            if "Simplified New York" not in prompt and "simplified" not in prompt.lower():
                issues.append(f"Page {i+1}: missing simplified background requirement")
            if "yellow cape" not in prompt.lower():
                issues.append(f"Page {i+1}: missing yellow cape costume lock")
            if first_lock is None:
                first_lock = THUNDER_VOLT_CHARACTER_LOCK
            elif THUNDER_VOLT_CHARACTER_LOCK not in prompt:
                issues.append(f"Page {i+1}: Thunder Volt lock text drifted")
        else:
            # Non-bank products must stay isolated from Thunder Volt / robber LOCK blocks.
            if THUNDER_VOLT_CHARACTER_LOCK in prompt or "THUNDER VOLT CHARACTER LOCK" in prompt:
                issues.append(f"Page {i+1}: Thunder Volt lock leaked into unrelated theme")
            if ROBBER_ONE_LOCK in prompt or "ROBBER ONE LOCK" in prompt:
                issues.append(f"Page {i+1}: robber lock leaked into unrelated theme")
            if "large open coloring" not in prompt.lower():
                issues.append(f"Page {i+1}: missing large open coloring requirement")
            if is_farm_theme(theme):
                low = prompt.lower()
                if not any(
                    phrase in low
                    for phrase in (
                        "do not draw the farmer",
                        "do not include the farmer",
                        "do not put the farmer",
                        "no farmer",
                    )
                ):
                    issues.append(f"Page {i+1}: farm interior missing no-farmer rule")
        # Farm interiors intentionally omit the full cover-theme sentence so the
        # model does not redraw the porch/farmer/dog on every page.
        if theme and theme.lower() not in prompt.lower() and not is_farm_theme(theme):
            issues.append(f"Page {i+1}: full user theme missing")
    return issues
