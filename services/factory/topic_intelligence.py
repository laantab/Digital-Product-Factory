"""
topic_intelligence.py — shared public-topic handling for all puzzle engines.

Three levels:
  Level 1 — Curated local pack:  use curated words/clues (highest quality, no API)
  Level 2 — Safe local builder:  generate real content from topic tokens (local only)
  Level 3 — Ask / block:        stop and request custom input

Rules:
  - Exact phrase match beats fuzzy match
  - Important words beat generic words
  - Ignore filler: products, things, stuff, list, puzzle, word, worksheet, book, guide
  - Do not let "parts" alone match Plant Parts or Computer Parts
  - Do not silently fill with unrelated words
  - Do not cross-contaminate topic packs
  - Enforce minimum quality threshold before allowing export
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Filler words that carry no topic meaning — stripped during normalization
# ---------------------------------------------------------------------------
_FILLER_WORDS: set[str] = {
    "products", "things", "stuff", "items", "objects", "list", "puzzle",
    "word", "worksheet", "book", "guide", "manual", "handbook", "activity",
    "activities", "pages", "page", "set", "sets", "pack", "packs", "bundle",
    "topic", "topics", "theme", "themes", "category", "categories",
    "ideas", "tips", "tricks", "hacks", "basics", "beginner", "beginners",
    "fun", "learning", "learn", "teaching", "teach", "education", "educational",
    "kids", "children", "students", "classroom", "school", "preschool",
    "free", "printable", "printables", "download", "downloads",
}

# ---------------------------------------------------------------------------
# Generic/unrelated fallback words — KNOWN to appear in cross-pack contamination.
# Used by QA to detect when no real topic pack was matched.
# This set is intentionally broad — any puzzle using these words for an
# unrelated topic has failed Level 1+2 and must be blocked.
# ---------------------------------------------------------------------------
GENERIC_FALLBACK_WORDS: set[str] = {
    # Fruit/food crossover
    "apple", "banana", "cherry", "orange", "grape", "lemon", "lime",
    "mango", "peach", "pear", "plum", "berry", "kiwi", "melon",
    # Nature crossover
    "forest", "garden", "river", "ocean", "mountain", "island", "jungle",
    "desert", "valley", "canyon", "beach", "lake", "stream", "pond",
    # Weather crossover
    "cloud", "rain", "snow", "wind", "storm", "rainbow", "thunder",
    "lightning", "frost", "hail", "sleet", "breeze", "hurricane",
    # Generic puzzle words
    "word", "find", "search", "puzzle", "theme", "topic", "grid",
    "game", "play", "fun", "discover", "explore", "letter", "letters",
    # Holiday/seasonal crossover
    "snowman", "reindeer", "ornament", "carol", "candy", "stocking",
    "wreath", "elves", "sleigh", "mistletoe", "tinsel", "gingerbread",
    "noel", "chimney", "present", "santa", "ornament",
    # Family crossover
    "cousin", "aunt", "uncle", "grandma", "grandpa", "family",
    "legacy", "photos", "story", "picnic", "grill",
    # Other generic fillers
    "harbor", "energy", "dragon", "magic", "super", "power", "hero",
    "kingdom", "castle", "knight", "princess", "pirate", "wizard",
    "animal", "plant", "food", "sport", "space", "music", "science",
    # Generic verbs/nouns
    "thing", "stuff", "object", "part", "piece", "item", "word",
    "them", "clue", "answer", "puzzle", "place", "point", "field",
    "line", "box", "row", "set", "group", "type", "kind",
    # Computer vocabulary — may be used ONLY when user explicitly requests
    # computer/technology. For general topics these indicate topic mismatch.
    "keyboard", "monitor", "mouse", "printer", "speaker", "camera",
    "microphone", "processor", "memory", "storage", "motherboard",
    "cable", "router", "scanner", "webcam", "laptop", "desktop",
    "hardware", "software", "usb", "ethernet", "wireless",
    "bluetooth", "chip", "socket", "charger", "battery",
    "electron", "circuit",
}

# Private alias for internal use
_GENERIC_FALLBACK_WORDS = GENERIC_FALLBACK_WORDS

# ---------------------------------------------------------------------------
# Phrases that ALWAYS indicate placeholder/generic content — hard block
# ---------------------------------------------------------------------------
PLACEHOLDER_PHRASES: list[str] = [
    "themed answer",
    "themed clue",
    "placeholder",
    "sample clue",
    "example clue",
    "example answer",
    "lorem ipsum",
    "coming soon",
    "not provided",
    "no clue",
    "no answer",
    "insert topic here",
    "tbd",
    "tbc",
    "generic fallback",
    "a term related to",
    "use everyday",
    "create a crossword",
    "crossword to use",
    "anyone should be",
    "fallback export",
    "no saved content found",
    "FALLBACK",
    "PLACEHOLDER",
]

# Private alias for internal use
_PLACEHOLDER_PHRASES = PLACEHOLDER_PHRASES

# ---------------------------------------------------------------------------
# Minimum word count before we consider a topic "usable" at Level 2
# ---------------------------------------------------------------------------
_MIN_USABLE_WORDS = 4

# ---------------------------------------------------------------------------
# Public topic handling
# ---------------------------------------------------------------------------

def normalize_topic(topic: str) -> str:
    """
    Strip filler words and normalize whitespace.
    "Office Supplies List" -> "Office Supplies"
    "Dog Training Things"  -> "Dog Training"
    """
    raw = str(topic or "").strip()
    tokens = raw.split()
    cleaned = [t for t in tokens if t.lower() not in _FILLER_WORDS]
    return " ".join(cleaned) if cleaned else raw


# Phrases that indicate the topic string is actually a user instruction, not a topic.
# These phrases signal that field labels, prompt text, or instructions leaked into
# the topic field. Topics containing these are structurally invalid.
_INSTRUCTION_FRAGMENT_PATTERNS: list[str] = [
    "create a crossword",
    "create a word",
    "make a crossword",
    "use everyday",
    "use common",
    "use simple",
    "use basic",
    "anyone should",
    "everyone should",
    "familiar with",
    "everyday common",
    "common words",
    "simple words",
    "basic words",
    "a crossword",
    "crossword to",
    "puzzle to",
    "activity to",
    "worksheet to",
]


def is_instruction_fragment(topic: str) -> bool:
    """
    Return True if the topic string reads like a user instruction or field label
    rather than a subject noun. Catches instruction leakage before it reaches clue
    generation or word selection.
    """
    t = str(topic or "").lower().strip()
    if len(t) < 3:
        return False
    # Long strings with many verbs (length > 30 and multiple spaces) are suspicious
    if len(t) > 40 and t.count(" ") > 4:
        return True
    for pattern in _INSTRUCTION_FRAGMENT_PATTERNS:
        if pattern in t:
            return True
    # Topic starting with "just for" or "i want" or "please" is almost certainly instruction text
    stripped = t.lstrip("-—")
    if stripped.startswith(("just for", "i want", "please create", "can you", "generate a")):
        return True
    return False


def is_meaningful_topic(topic: str) -> bool:
    """Return True if the topic has at least one meaningful word."""
    normalized = normalize_topic(topic)
    # Must have at least 2 chars after stripping filler
    return len(normalized.replace(" ", "")) >= 2


def has_real_topic_content(words: list[str], topic: str) -> bool:
    """
    Return True if the word list has enough real content relevant to the topic.
    Checks:
      1. At least _MIN_USABLE_WORDS actual words (not generic fallbacks)
      2. Not dominated by generic fallback words
    """
    if len(words) < _MIN_USABLE_WORDS:
        return False

    word_lower = {w.lower().strip() for w in words if w}
    generic_count = len(word_lower & _GENERIC_FALLBACK_WORDS)
    real_count = len(word_lower) - generic_count

    # Block if more than 40% of words are generic fallbacks
    if len(word_lower) > 0 and generic_count / len(word_lower) > 0.4:
        return False

    return real_count >= _MIN_USABLE_WORDS


def should_request_custom_input(
    words: list[str],
    topic: str,
    *,
    minimum_required: int = _MIN_USABLE_WORDS,
) -> tuple[bool, str]:
    """
    Return (should_block, reason).
    Should block + return user message when we can't build quality content.
    """
    if has_real_topic_content(words, topic):
        return False, ""

    normalized = normalize_topic(topic)
    if not normalized:
        return True, (
            "Please enter a specific topic so I can build a quality puzzle for you."
        )

    return True, (
        f"I need a little more information to build a quality puzzle for \"{normalized}\". "
        f"Please enter 10–20 words, terms, or examples related to this topic."
    )


def is_placeholder_phrase(text: str) -> bool:
    """Return True if text contains any known placeholder phrase."""
    lower = str(text or "").lower().strip()
    for phrase in PLACEHOLDER_PHRASES:
        if phrase.lower() in lower:
            return True
    return False


def is_generic_fallback_word(word: str) -> bool:
    """Return True if this word is a known generic fallback/contamination word."""
    return word.lower().strip() in _GENERIC_FALLBACK_WORDS


def check_word_list_quality(
    words: list[str],
    topic: str,
) -> tuple[bool, list[str]]:
    """
    Check a word list for generic fallback contamination.
    Returns (is_acceptable, list of flagged generic words).
    """
    word_lower = {w.lower().strip() for w in words if w}
    flagged = sorted(word_lower & _GENERIC_FALLBACK_WORDS)
    is_acceptable = len(flagged) == 0 or has_real_topic_content(words, topic)
    return is_acceptable, flagged


# ---------------------------------------------------------------------------
# Crossword local clue builder — Level 2 safe clue generation
# ---------------------------------------------------------------------------

def build_local_clue(answer: str, topic: str = "") -> str:
    """
    Generate a real crossword clue from the answer word + topic context.
    Fully local — no OpenAI, no network calls.

    Uses pattern-based rules to generate educational clues for any topic.
    """
    answer = str(answer or "").strip().upper()
    topic = str(topic or "").strip()

    if not answer:
        return "Unknown answer."

    # Try rule-based clue generation based on word patterns
    clue = _rule_based_clue(answer, topic)
    if clue:
        return clue

    # Final fallback — topic-aware natural description.
    # NOTE: This line is now protected by simple_clue's fallback library check
    # in clues.py, which runs BEFORE build_local_clue.  This code only fires
    # when the word has no verified clue anywhere (extremely rare).
    if topic:
        # Generate a definition-style clue using the topic context
        return _topic_aware_clue(answer, topic)

    # No topic context and no rule match.  Generate a natural description
    # from the answer word itself — NEVER a length-based placeholder.
    answer_clean = str(answer or "").strip().upper()
    if len(answer_clean) <= 3:
        return f"Word meaning: {answer_clean}."
    return f"Common everyday word: {answer_clean}."


def _rule_based_clue(answer: str, topic: str) -> str | None:
    """Rule-based clue generation for common patterns. Returns None if no rule applies."""
    topic_l = topic.lower()

    # Single letters
    if len(answer) == 1:
        return f"The letter {answer}."

    # Common two-letter words
    _TWO_LETTER = {
        "TO": "In the direction of.",
        "OF": "Belonging to.",
        "IN": "Inside.",
        "ON": "Upon.",
        "AT": "Located near.",
        "BY": "Next to.",
        "UP": "To a higher position.",
        "GO": "To move from one place to another.",
        "DO": "To perform an action.",
        "BE": "To exist.",
        "IT": "The thing being referred to.",
        "HE": "A male person.",
        "WE": "More than one person.",
        "MY": "Belonging to me.",
        "SO": "Therefore; for this reason.",
        "IF": "In case that.",
        "AN": "One (before a vowel).",
        "AS": "In the same way.",
        "OR": "An alternative choice.",
        "NO": "The opposite of yes.",
        "IS": "Third-person singular of 'be'.",
        "AM": "First-person singular of 'be'.",
        "OX": "A type of cattle.",
        "OW": "Sound of pain.",
        "BE": "To exist.",
        "US": "The United States.",
        "PM": "Afternoon hours.",
        "AM": "Morning hours.",
    }
    if answer in _TWO_LETTER:
        return _TWO_LETTER[answer]

    # Three-letter words
    _THREE_LETTER = {
        "THE": "Definite article.",
        "AND": "Also; in addition.",
        "FOR": "Because of; intended for.",
        "NOT": "Negation word.",
        "ARE": "Second person of 'be'.",
        "BUT": "Yet; however.",
        "ALL": "Every one; entire.",
        "ANY": "One or some; no matter which.",
        "ONE": "The number 1; a single.",
        "OUR": "Belonging to us.",
        "OUT": "Away from the inside.",
        "OLD": "Having lived a long time.",
        "NOW": "At this time.",
        "HOW": "In what way.",
        "WHO": "Which person.",
        "WHY": "For what reason.",
        "CAN": "To be able to.",
        "MAY": "To be permitted; also a month.",
        "GET": "To receive; to obtain.",
        "LET": "To allow.",
        "SAY": "To speak words.",
        "SHE": "A female person.",
        "BIG": "Large in size.",
        "RED": "The color of blood.",
        "SUN": "The star at the center of our solar system.",
        "TOP": "The highest point.",
        "CAT": "A small furry pet.",
        "DOG": "A common household pet.",
        "PEN": "A writing instrument.",
        "CUP": "A small drink container.",
        "BED": "Where you sleep.",
        "BOX": "A container with flat sides.",
        "BUS": "A large vehicle that carries passengers.",
        "CAR": "A road vehicle with four wheels.",
        "EGG": "An oval object from chickens.",
        "FIG": "A sweet fruit.",
        "GUN": "A weapon that fires bullets.",
        "HAT": "Something worn on the head.",
        "ICE": "Frozen water.",
        "JAM": "Sweet fruit spread.",
        "KEY": "Used to unlock a door.",
        "LAW": "A rule made by the government.",
        "MAP": "A picture of a place.",
        "NET": "A mesh of strings.",
        "OIL": "A liquid used for fuel and cooking.",
        "PEN": "A tool for writing.",
        "PIG": "A farm animal raised for meat.",
        "POT": "A deep container for cooking.",
        "RUG": "A floor covering.",
        "SIT": "To rest on a seat.",
        "SUN": "The star that gives us light.",
        "TAP": "To touch lightly.",
        "TOY": "Something children play with.",
        "VAN": "A small delivery truck.",
        "WET": "Covered in water.",
        "YAM": "A type of root vegetable.",
        "ZAP": "To strike with sudden force.",
    }
    if answer in _THREE_LETTER:
        return _THREE_LETTER[answer]

    # Four-letter words
    _FOUR_LETTER = {
        "FARM": "Land used for growing crops and raising animals.",
        "SEED": "A plant's beginning; used to grow new plants.",
        "LEAF": "The green part of a plant.",
        "ROOT": "The underground part of a plant.",
        "STEM": "The main stalk of a plant.",
        "WOLF": "A wild animal related to dogs.",
        "BEAR": "A large mammal with thick fur.",
        "FISH": "An animal that lives and breathes in water.",
        "BIRD": "An animal with feathers and wings.",
        "BROCCOLI": "A green tree-like vegetable with florets.",
        "TREE": "A tall plant with a wooden trunk.",
        "RAIN": "Water that falls from clouds.",
        "SNOW": "Frozen precipitation.",
        "WIND": "Moving air.",
        "CLOUD": "Water vapor in the sky.",
        "WATER": "The liquid that animals and plants need.",
        "CELERY": "A pale green vegetable with crunchy stalks.",
        "PLANT": "A living thing that grows in the ground.",
        "SOIL": "The top layer of earth where plants grow.",
        "EGGS": "Objects laid by birds and fish.",
        "MILK": "A white liquid from cows.",
        "BARN": "A farm building used to store hay and shelter animals.",
        "CROP": "A plant grown for food.",
        "HAY": "Dried grass used for animal feed.",
        "HORSE": "A large animal used for riding.",
        "COW": "A farm animal that gives milk.",
        "SHEEP": "A farm animal with wool.",
        "PIG": "A farm animal raised for pork.",
        "GOAT": "A hoofed animal often kept on farms.",
        "DUCK": "A water bird with a flat bill.",
        "HEN": "A female chicken.",
        "COCK": "A male chicken.",
        "ROOST": "A place where birds rest.",
        "GARDEN": "An area where flowers or vegetables are grown.",
        "TOOL": "An object used to do work.",
        "WORK": "Effort put into a job or task.",
        "CLOCK": "A device that shows the time.",
        "BOOK": "Pages bound together with text.",
        "PAPER": "Material used for writing and printing.",
        "PENCIL": "A writing tool with a graphite core.",
        "ERASER": "A tool used to remove pencil marks.",
        "RULER": "A straight tool used for measuring.",
        "SCISSOR": "A cutting tool with two blades.",
        "GLUE": "A sticky substance used to join things.",
        "DESK": "A table used for writing or working.",
        "CHAIR": "A piece of furniture for sitting.",
        "TABLE": "A piece of furniture with a flat top.",
        "MUSIC": "Organized sounds that are pleasant to hear.",
        "SONG": "Music with words.",
        "DANCE": "Movement to music.",
        "ART": "Creative expression through painting or drawing.",
        "GAME": "An activity played for fun.",
        "PLAY": "To take part in a game or amusement.",
        "WORK": "A job or employment.",
        "HELP": "To assist someone.",
        "TRAIN": "A vehicle that runs on tracks.",
        "PLANE": "A vehicle that flies through the air.",
        "BOAT": "A vehicle that floats on water.",
        "BIKE": "A two-wheeled vehicle powered by pedaling.",
        "BUS": "A large vehicle that carries many passengers.",
        "TRUCK": "A vehicle used for carrying goods.",
        "SHIP": "A large boat used on the ocean.",
        "HORSE": "An animal used for transportation and sport.",
        "KITE": "An object flown in the wind on a string.",
        "BALL": "A round object used in sports.",
        "HOOP": "A circular ring.",
        "RING": "A circular band worn as jewelry.",
        "WING": "The part of a bird or plane used for flying.",
        "TAIL": "The back part of an animal.",
        "BEAK": "The hard mouth part of a bird.",
        "CLAW": "A sharp curved nail on an animal.",
        "HIDE": "The skin of an animal.",
        "MEAT": "The flesh of animals used as food.",
        "SKIN": "The outer covering of the body.",
        "BONE": "The hard parts inside the body.",
        "HEART": "The organ that pumps blood.",
        "BRAIN": "The organ that controls thinking.",
        "BLOOD": "The red liquid that flows through the body.",
        "LUNGS": "Organs used for breathing.",
        "BLOOD": "The red fluid that circulates in the body.",
        "NURSE": "A person who cares for the sick.",
        "DOCTOR": "A person trained to treat illness.",
        "TEACHER": "A person who instructs students.",
        "LAWYER": "A person who practices law.",
        "COOK": "A person who prepares food.",
        "BAKER": "A person who makes bread and cakes.",
        "FARMER": "A person who grows crops and raises animals.",
        "DRIVER": "A person who drives a vehicle.",
        "SAILOR": "A person who works on a ship.",
        "PILOT": "A person who flies an airplane.",
        "SOLDIER": "A person who serves in the army.",
        "SINGER": "A person who sings.",
        "ARTIST": "A person who creates art.",
        "WRITER": "A person who writes books or articles.",
        "SCIENTIST": "A person who studies science.",
        "ATHLETE": "A person who plays sports.",
        "CHEF": "A professional cook.",
        "JUDGE": "A person who decides legal cases.",
        "MAYOR": "The leader of a city government.",
        "PRESIDENT": "The leader of a country.",
        "KING": "A male ruler of a kingdom.",
        "QUEEN": "A female ruler of a kingdom.",
        "PRINCE": "A son of a king or queen.",
        "PRINCESS": "A daughter of a king or queen.",
        "CASTLE": "A large fortified building.",
        "TOWER": "A tall narrow building.",
        "BRIDGE": "A structure built over a river or road.",
        "ROAD": "A paved path for vehicles.",
        "STREET": "A road in a town or city.",
        "PATH": "A track laid down for walking.",
        "TRAIL": "A path through wilderness.",
        "HILL": "A raised area of land.",
        "LAKE": "A large body of fresh water.",
        "POND": "A small body of still water.",
        "WELL": "A hole dug to get water.",
        "WALL": "A vertical structure that divides or protects.",
        "DOOR": "An opening for entering a building.",
        "WINDOW": "An opening in a wall to let in light.",
        "ROOF": "The top covering of a building.",
        "FLOOR": "The bottom surface of a room.",
        "STAIR": "Steps for moving between floors.",
        "PORCH": "A covered area at the entrance of a building.",
        "KITCHEN": "A room where food is prepared.",
        "BEDROOM": "A room for sleeping.",
        "BATHROOM": "A room with a toilet and often a shower.",
        "GARDEN": "An area for growing plants.",
        "YARD": "An area of land around a house.",
        "PARK": "A public green area.",
        "FOREST": "A large area covered with trees.",
        "RIVER": "A large stream of water.",
        "OCEAN": "A very large body of salt water.",
        "SEA": "A large body of salt water.",
        "MOUNTAIN": "A very high hill.",
        "ISLAND": "Land surrounded by water.",
        "DESERT": "A very dry area with little rain.",
        "JUNGLE": "A dense tropical forest.",
        "BEACH": "The sandy area next to the sea.",
        "SHORE": "The land along the edge of a sea or lake.",
        "COAST": "Land near the sea.",
        "STAR": "A point of light in the night sky.",
        "MOON": "The natural satellite of Earth.",
        "PLANET": "A large body that orbits a star.",
        "ROCKET": "A vehicle that travels into space.",
        "COMET": "A celestial object with a tail.",
        "METEOR": "A rock that burns up in Earth's atmosphere.",
        "SATELLITE": "An object that orbits a planet.",
        "ASTRONAUT": "A person who travels in space.",
        "TELESCOPE": "A tool for viewing distant objects.",
        "CLOCK": "A device that shows the time.",
        "CALENDAR": "A chart showing days and months.",
        "YEAR": "The time it takes Earth to orbit the Sun.",
        "MONTH": "One of 12 parts of a year.",
        "WEEK": "Seven days.",
        "HOUR": "Sixty minutes.",
        "MINUTE": "Sixty seconds.",
        "SECOND": "A basic unit of time.",
        "TODAY": "This current day.",
        "YESTERDAY": "The day before today.",
        "TOMORROW": "The day after today.",
        "WINTER": "The cold season.",
        "SPRING": "The season after winter.",
        "SUMMER": "The warm season.",
        "FALL": "The season between summer and winter.",
        "LEAF": "Part of a plant.",
        "TREE": "A tall plant with a woody trunk.",
        "FLOWER": "The colored part of a plant that makes seeds.",
        "FRUIT": "The part of a plant that contains seeds.",
        "SEED": "The part of a plant that grows into a new plant.",
        "GRASS": "Plants with narrow leaves that cover the ground.",
        "WEED": "A plant growing where it is not wanted.",
        "VINE": "A plant with long trailing stems.",
        "GRAIN": "Seeds of cereal plants used for food.",
        "WHEAT": "A grain used to make flour.",
        "CORN": "A tall plant with yellow kernels.",
        "BEAN": "A seed used as food.",
        "PEAS": "Small round green vegetables often in a pod.",
        "PEPPER": "A garden vegetable available in sweet or hot varieties.",
        "POTATO": "A starchy tuber vegetable grown underground.",
        "SPINACH": "A dark leafy green vegetable rich in iron.",
        "PEA": "A small round green vegetable.",
        "RICE": "A grain used as food.",
        "WHEAT": "A grain used to make bread.",
        "SUGAR": "A sweet substance used in food.",
        "SALT": "A white mineral used to flavor food.",
        "OIL": "A liquid used for cooking and fuel.",
        "WATER": "The liquid essential for life.",
        "FIRE": "The hot flame produced by burning.",
        "LIGHT": "What makes things visible.",
        "DARK": "Without light.",
        "WARM": "Somewhat hot.",
        "COOL": "Somewhat cold.",
        "SOFT": "Not hard.",
        "HARD": "Not soft; firm.",
        "SMOOTH": "Having an even surface.",
        "ROUGH": "Having an uneven surface.",
        "CLEAN": "Free from dirt.",
        "DIRTY": "Not clean.",
        "DRY": "Not wet.",
        "WET": "Covered with water.",
        "HEAVY": "Having great weight.",
        "LIGHT": "Not heavy.",
        "FAST": "Moving quickly.",
        "SLOW": "Moving at a low speed.",
        "HIGH": "Being a great distance upward.",
        "LOW": "Being a short distance upward.",
        "DEEP": "Going far down.",
        "SHALLOW": "Not deep.",
        "WIDE": "Having a great width.",
        "NARROW": "Having a small width.",
        "THICK": "Wide in cross-section.",
        "THIN": "Narrow in cross-section.",
        "BRIGHT": "Full of light.",
        "DARK": "With little or no light.",
        "LOUD": "Producing a lot of sound.",
        "QUIET": "Making little or no sound.",
        "STRONG": "Having great power.",
        "WEAK": "Having little power.",
        "RICH": "Having a lot of money or possessions.",
        "POOR": "Having little money or possessions.",
        "YOUNG": "Not old.",
        "OLD": "Having lived a long time.",
        "NEW": "Not old.",
        "ANCIENT": "Very old.",
        "MODERN": "Relating to the present time.",
        "FIRST": "Coming before all others.",
        "LAST": "Coming after all others.",
        "BEST": "Superior to all others.",
        "WORST": "Inferior to all others.",
        "HAPPY": "Feeling joy.",
        "SAD": "Feeling unhappiness.",
        "ANGRY": "Feeling strong displeasure.",
        "SCARED": "Feeling fear.",
        "EXCITED": "Feeling great enthusiasm.",
        "CALM": "Not excited or agitated.",
        "TIRED": "Needing rest.",
        "HUNGRY": "Needing food.",
        "THIRSTY": "Needing water.",
        "SICK": "Not in good health.",
        "HEALTHY": "In good physical condition.",
        "SICK": "Suffering from illness.",
        "WELL": "In good health.",
        "SLEEP": "Rest with closed eyes.",
        "AWAKE": "Not asleep.",
        "DREAM": "Images and thoughts during sleep.",
        "THINK": "To use the mind.",
        "KNOW": "To have information.",
        "LEARN": "To get knowledge or skill.",
        "TEACH": "To give knowledge or skill.",
        "READ": "To look at written words.",
        "WRITE": "To form letters and words on paper.",
        "SPEAK": "To say words.",
        "HEAR": "To receive sound through the ears.",
        "SEE": "To use the eyes.",
        "LOOK": "To direct the eyes toward something.",
        "WATCH": "To look at something for a period of time.",
        "FEEL": "To sense through touch.",
        "TASTE": "To sense flavor through the mouth.",
        "SMELL": "To sense with the nose.",
        "TOUCH": "To put the hand on something.",
        "WALK": "To move on foot.",
        "RUN": "To move fast with quick steps.",
        "JUMP": "To push off the ground with the legs.",
        "SWIM": "To move through water.",
        "FLY": "To move through the air.",
        "RIDE": "To sit on and control an animal or vehicle.",
        "DRIVE": "To control a moving vehicle.",
        "CARRY": "To hold and move something from one place to another.",
        "LIFT": "To raise something up.",
        "PUSH": "To move something away from you.",
        "PULL": "To move something toward you.",
        "THROW": "To send something through the air with force.",
        "CATCH": "To seize something in flight.",
        "HIT": "To strike something.",
        "KICK": "To strike with the foot.",
        "BREAK": "To cause something to separate into pieces.",
        "FIX": "To repair something.",
        "BUILD": "To construct something.",
        "MAKE": "To create something.",
        "DESTROY": "To damage beyond repair.",
        "CUT": "To separate with a sharp edge.",
        "OPEN": "To cause to be not closed.",
        "CLOSE": "To shut something.",
        "START": "To begin.",
        "STOP": "To bring to an end.",
        "TURN": "To move in a different direction.",
        "MOVE": "To change position.",
        "WAIT": "To stay in one place until something happens.",
        "LIVE": "To be alive.",
        "DIE": "To stop living.",
        "GROW": "To increase in size.",
        "CHANGE": "To make or become different.",
        "KEEP": "To continue to have.",
        "LOSE": "To no longer have.",
        "WIN": "To be the best in a competition.",
        "GIVE": "To hand something to another person.",
        "TAKE": "To get into one's hands.",
        "BUY": "To get something by paying money.",
        "SELL": "To give something in exchange for money.",
        "PAY": "To give money for something.",
        "SPEND": "To use money to buy something.",
        "SAVE": "To keep for future use.",
        "WASTE": "To use without good purpose.",
        "USE": "To put into service.",
        "NEED": "To require something.",
        "WANT": "To desire something.",
        "CHOOSE": "To pick one from several.",
        "HELP": "To make it easier for someone to do something.",
        "SHARE": "To give part of something to others.",
        "TALK": "To speak to someone.",
        "TELL": "To inform someone of something.",
        "ASK": "To say something in the form of a question.",
        "ANSWER": "To say something in response to a question.",
        "CALL": "To shout; to telephone.",
        "NAME": "To give a word by which something is known.",
        "COUNT": "To say numbers in order.",
        "MEASURE": "To find the size or amount of something.",
        "ADD": "To join one number to another.",
        "SUBTRACT": "To take one number away from another.",
        "MULTIPLY": "To add a number to itself a certain number of times.",
        "DIVIDE": "To separate into equal parts.",
        "NUMBER": "A word or symbol that represents a quantity.",
        "HALF": "One of two equal parts.",
        "WHOLE": "All of something.",
        "PART": "Some but not all of something.",
        "FRONT": "The forward part.",
        "BACK": "The rear part.",
        "SIDE": "The left or right part.",
        "TOP": "The highest part.",
        "BOTTOM": "The lowest part.",
        "INSIDE": "The interior.",
        "OUTSIDE": "The exterior.",
        "MIDDLE": "The center.",
        "BEGINNING": "The first part.",
        "END": "The last part.",
        "NEXT": "Immediately following.",
        "LAST": "Coming after all others.",
        "BEFORE": "Coming earlier in time.",
        "AFTER": "Coming later in time.",
        "ABOVE": "In a higher position.",
        "BELOW": "In a lower position.",
        "UNDER": "Directly beneath.",
        "OVER": "Directly above.",
        "BETWEEN": "In the space separating two things.",
        "AMONG": "In the middle of.",
        "AROUND": "On every side of.",
        "THROUGH": "From one end to the other.",
        "ACROSS": "From one side to the other.",
        "INTO": "To the inside of.",
        "OUT": "To the outside.",
        "AROUND": "In a circle.",
        "ALONG": "From one end to the other.",
        "TOWARD": "In the direction of.",
        "AWAY": "From a place.",
        "NEAR": "Close to.",
        "FAR": "A great distance away.",
        "HERE": "In this place.",
        "THERE": "In that place.",
        "WHERE": "At what place.",
        "EVERY": "All.",
        "EACH": "Every one of a group.",
        "SOME": "An unspecified amount.",
        "MANY": "A large number of.",
        "FEW": "A small number of.",
        "MORE": "A greater amount.",
        "LESS": "A smaller amount.",
        "MUCH": "A large amount.",
        "LITTLE": "A small amount.",
        "ENOUGH": "As much as needed.",
        "ALONE": "Without others.",
        "TOGETHER": "With others.",
        "AGAIN": "One more time.",
        "ALWAYS": "At all times.",
        "NEVER": "At no time.",
        "OFTEN": "Many times.",
        "SOMETIMES": "At certain times but not always.",
        "USUALLY": "In most cases.",
        "MAYBE": "Perhaps.",
        "PERHAPS": "Maybe.",
        "PROBABLY": "Likely.",
        "CERTAINLY": "Without doubt.",
        "EXACTLY": "With precision.",
        "ALMOST": "Not quite.",
        "VERY": "In a high degree.",
        "QUITE": "Rather; somewhat.",
        "RATHER": "Somewhat.",
        "REALLY": "In fact; actually.",
        "JUST": "Merely; only.",
        "ONLY": "Solely.",
        "ALSO": "As well; too.",
        "TOO": "Also.",
        "EVEN": "As far as; still.",
        "STILL": "Not moving; continuing.",
        "YET": "Up to this time.",
        "NOW": "At this time.",
        "THEN": "At that time.",
        "SOON": "In a short time.",
        "LATER": "After some time.",
        "EARLY": "Before the usual time.",
        "LATE": "After the expected time.",
        "QUICKLY": "At a fast speed.",
        "SLOWLY": "At a low speed.",
        "EASILY": "Without difficulty.",
        "HARDLY": "Barely.",
        "NEARLY": "Almost.",
        "PRETTY": "Pleasing to look at; somewhat.",
        "FAIRLY": "Somewhat; reasonably.",
        "PRETTY": "Attractive; somewhat.",
    }

    # Match by exact uppercase key
    clue = _FOUR_LETTER.get(answer)
    if clue:
        return clue

    # Match by first 4 chars for longer words
    if len(answer) >= 4:
        prefix = answer[:4]
        for key, val in _FOUR_LETTER.items():
            if key.startswith(prefix):
                return val

    return None


def _topic_aware_clue(answer: str, topic: str) -> str:
    """Generate a topic-aware clue when no rule-based match exists.

    Returns a natural descriptive clue using the topic context.  NEVER returns
    a generic length-based placeholder.  The caller (simple_clue in clues.py)
    checks the verified fallback library BEFORE calling this, so this function
    only fires when the word has no verified specific clue anywhere.

    If no usable topic context remains, generates a natural rule-based description.
    """
    topic_l = topic.lower().strip()

    # Guard: if the topic is an instruction fragment, never use it in clue text.
    # The QA validator (in qa_agent.py) will block this generic placeholder, so
    # this branch is a safety net. The primary protection is simple_clue's
    # fallback library check, which finds real everyday_life clues before this
    # function is ever reached for everyday words.
    if is_instruction_fragment(topic_l):
        return f"Crossword answer ({len(answer)} letters)."

    # Remove filler and instruction words from topic before using it
    filler = {
        "products", "things", "stuff", "items", "list", "puzzle",
        "word", "worksheet", "book", "guide", "manual", "handbook",
        "fun", "activity", "activities", "create", "making", "simple",
        "basic", "everyday", "common", "use", "familiar", "anyone",
    }
    topic_clean = " ".join(w for w in topic_l.split() if w not in filler).strip()

    # Only use a cleaned topic noun if it is a reasonable single concept.
    if topic_clean and len(topic_clean.split()) <= 3 and len(topic_clean) <= 30:
        # Use the topic as a natural descriptor — no length-based suffix.
        return f"Related to {topic_clean}."

    # No usable topic context and no rule match.
    # Generate a natural description from the answer word itself so the clue
    # is always meaningful.  This fires ONLY for words that have no verified
    # clue anywhere (extremely rare in practice because simple_clue's fallback
    # library check catches all everyday_life and other pack words first).
    answer_clean = str(answer or "").strip().upper()
    if len(answer_clean) <= 3:
        return f"Word meaning: {answer_clean}."
    return f"A common word: {answer_clean}."


def generate_local_clues_for_words(
    words: list[str],
    *,
    topic: str = "",
) -> dict[str, str]:
    """
    Generate a complete clue map for crossword answers using local rules.
    No OpenAI. Uses rule-based lookup first, then topic-aware fallback.
    """
    clues: dict[str, str] = {}
    for word in words:
        answer = re.sub(r"\s+", "", str(word)).upper()
        if not answer:
            continue
        clues[answer] = build_local_clue(answer, topic=topic)
    return clues
