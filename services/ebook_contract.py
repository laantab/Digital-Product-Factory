"""
Ebook Generation Contract.

Before generating any ebook content, a contract is built that defines what the ebook
must contain, what it must avoid, and what disclaimers are required. The contract
guides the AI generator, visual plan, QA agent, and any downstream output.

No external API calls — pure Python, fully deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Risk category detection
# ---------------------------------------------------------------------------

RISK_CATEGORIES = frozenset({
    "health", "fitness", "weight_loss", "medical",
    "finance", "financial", "legal", "taxes", "investing",
    "safety", "mental_health", "therapy",
})

RISK_KEYWORDS = {
    "health":      {"health", "wellness", "disease", "illness", "treatment", "diagnosis", "symptom"},
    "fitness":     {"fitness", "exercise", "workout", "training", "muscle", "strength", "cardio"},
    "weight_loss": {"weight loss", "lose weight", "burn fat", "slim", "diet", "calorie", "belly fat", "overweight"},
    "medical":     {"medical", "doctor", "prescription", "medication", "therapy", "clinical", "patient", "sleep", "insomnia", "fatigue"},
    "finance":     {"finance", "financial", "money", "invest", "stock", "portfolio", "retirement", "income", "debt", "credit"},
    "legal":       {"legal", "law", "attorney", "court", "rights", "contract", "liability"},
    "taxes":       {"tax", "irs", "taxes", "deduction", "audit"},
    "investing":    {"invest", "investment", "stock market", "crypto", "bond", "equity", "trading"},
    "safety":      {"safety", "hazard", "danger", "risk", "unsafe"},
}


def _detect_risk_category(topic: str, title: str = "", audience: str = "") -> list[str]:
    """Return a list of detected risk categories for a topic."""
    combined = f"{topic} {title} {audience}".lower()
    found: list[str] = []
    for category, keywords in RISK_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            found.append(category)
    return found


def _needs_disclaimer(topic: str, title: str = "", audience: str = "") -> bool:
    """True when the topic falls into a regulated category that requires a disclaimer."""
    return bool(_detect_risk_category(topic, title, audience))


# ---------------------------------------------------------------------------
# Standard disclaimer texts
# ---------------------------------------------------------------------------

DEFAULT_DISCLAIMER = (
    "The information in this book is provided for general educational and "
    "informational purposes only. It is not intended as a substitute for professional "
    "medical, financial, legal, or other qualified advice. Always consult a licensed "
    "professional before making health, financial, or legal decisions. "
    "The author and publisher make no warranties and accept no liability for any "
    "outcomes resulting from the use of this material."
)

HEALTH_DISCLAIMER = (
    "This book is for educational purposes only and is not intended to diagnose, "
    "treat, cure, or prevent any disease or medical condition. "
    "Consult your physician or a qualified healthcare provider before beginning "
    "any new exercise program, diet, or supplement regimen. "
    "Individual results vary."
)

FINANCE_DISCLAIMER = (
    "This book is for informational and educational purposes only and does not "
    "constitute financial, investment, or legal advice. "
    "All financial decisions should be made in consultation with a licensed "
    "financial advisor. "
    "Past performance is not indicative of future results. "
    "The author and publisher are not responsible for any losses incurred."
)

LEGAL_DISCLAIMER = (
    "This book is for informational purposes only and does not constitute legal advice. "
    "Laws vary by jurisdiction. Consult a licensed attorney for legal guidance specific "
    "to your situation."
)


def _build_disclaimer_text(topic: str, title: str = "", audience: str = "") -> str:
    """Return the appropriate disclaimer for a topic."""
    cats = _detect_risk_category(topic, title, audience)
    if "medical" in cats or "health" in cats or "fitness" in cats:
        return HEALTH_DISCLAIMER
    if "finance" in cats or "investing" in cats:
        return FINANCE_DISCLAIMER
    if "legal" in cats:
        return LEGAL_DISCLAIMER
    return DEFAULT_DISCLAIMER


# ---------------------------------------------------------------------------
# Claim safety — forbidden phrases
# ---------------------------------------------------------------------------

# Phrases that require actual evidence/research to use legitimately.
# These are flagged as errors if research was NOT requested.
UNSUPPORTED_CLAIM_PHRASES = frozenset({
    "scientifically proven",
    "clinically proven",
    "scientifically backed",
    "proven by research",
    "research proves",
    "studies show",
    "research shows",
    "clinical evidence",
    "cutting-edge research",
    "latest research",
    "thoroughly fact-checked",
    "fact-checked by",
    "fact checked by",
    "expert-reviewed",
    "medically approved",
    "doctor-approved",
    "FDA approved",
    "guaranteed results",
    "guaranteed to work",
    "lose weight fast",
    "effortless weight loss",
    "miracle",
    "secret method",
    "secret ingredient",
    "transform your body",
    "burn fat fast",
})


# Marketing phrases that are never acceptable regardless of research.
FOREVER_FORBIDDEN_MARKETING = frozenset({
    "lose weight fast",
    "effortless weight loss",
    "time's running out",
    "time is running out",
    "last chance",
    "secret",
    "guaranteed",
    "miracle cure",
    "instant results",
    "no effort required",
    "zero effort",
    "transform overnight",
    "cutting-edge research",
    "latest research",
    "fact-checked",
    "thoroughly fact-checked",
    "fact checked",
    "scientifically proven",
    "clinically proven",
})


# Safer marketing alternatives for use in product summaries.
SAFE_MARKETING_PHRASES = frozenset({
    "practical guide",
    "beginner-friendly",
    "step-by-step",
    "simple strategies",
    "realistic habits",
    "helpful worksheets",
    "clear examples",
    "easy-to-follow",
    "sustainable approach",
    "evidence-informed",
    "based on established principles",
})


# ---------------------------------------------------------------------------
# Chapter structure requirements
# ---------------------------------------------------------------------------

# Varied chapter craft — do NOT force identical H3 labels in every chapter.
REQUIRED_CHAPTER_ELEMENTS = [
    "a structure that fits THIS chapter's job (scenario, decision guide, checklist, script, routine, worksheet, or troubleshooting — vary across chapters)",
    "plain-English explanation specific to the topic and audience",
    "at least one concrete, usable example or dialogue (label fictional samples clearly)",
    "practical guidance the reader can try within 24 hours",
    "a descriptive closing label unique to the chapter (never reuse the generic phrase 'Chapter takeaway')",
]

# Phrases that must not appear as repeated H3 labels across a whole ebook.
FORBIDDEN_REPEATED_HEADINGS = [
    "What this chapter helps you solve and why it matters",
    "A step-by-step method",
    "Common mistakes",
    "Chapter takeaway",
]

# Generic filler phrases that indicate weak content.
GENERIC_FILLER_PHRASES = frozenset({
    "small steps matter",
    "you can do it",
    "remember, you're not alone",
    "this guide will help you succeed",
    "take it one step at a time",
    "stay motivated",
    "believe in yourself",
    "consistency is key",
    "keep going",
    "you're doing great",
    "every journey begins",
    "the power of now",
    "just start today",
    "change starts with you",
    "it's not about perfection",
    "progress over perfection",
    "trust the process",
    "you've got this",
})

# Placeholder/generic phrases that must never appear in finished content.
PLACEHOLDER_PHRASES = frozenset({
    "lorem ipsum",
    "insert topic here",
    "placeholder",
    "coming soon",
    "tbd",
    "tbc",
    "no saved content found",
    "fallback export",
    "this section is under construction",
    "generic fallback",
    "example placeholder",
    "main point of this chapter",
    "capture the core message",
    "the one takeaway from this chapter",
    "the one thing worth keeping",
    "pull out the core idea",
    "apply what you learned",
    "key takeaway",
})


# ---------------------------------------------------------------------------
# Contract dataclass
# ---------------------------------------------------------------------------

@dataclass
class EbookContract:
    topic: str
    audience: str = ""
    reader_problem: str = ""
    desired_transformation: str = ""
    reading_level: str = "General adult"
    tone: str = "professional"
    ebook_length: str = "standard"        # short / standard / comprehensive
    chapter_count: int = 6
    topic_category: str = "general"
    risk_categories: list[str] = field(default_factory=list)

    # Research flag — controls whether research-dependent claims are allowed.
    research_requested: bool = False

    # Claims
    claims_allowed: list[str] = field(default_factory=list)
    claims_forbidden: list[str] = field(default_factory=list)

    # Disclaimer
    disclaimer_required: bool = False
    disclaimer_text: str = ""

    # Chapter requirements
    required_chapter_angles: list[str] = field(default_factory=list)

    # Worksheet expectations
    worksheet_required: bool = False
    worksheet_expectation: str = ""

    # Marketing limits
    marketing_claim_limits: list[str] = field(default_factory=list)

    # Internal
    _is_fitness_topic: bool = False
    _is_health_topic: bool = False
    _is_finance_topic: bool = False
    _is_legal_topic: bool = False


def build_contract(
    topic: str,
    audience: str = "",
    tone: str = "professional",
    reading_level: str = "General adult",
    ebook_length: str = "standard",
    chapter_count: int = 6,
    research_requested: bool = False,
    reader_problem: str = "",
    desired_transformation: str = "",
    worksheet_required: bool = False,
    worksheet_expectation: str = "",
    override_disclaimer: str = "",
) -> EbookContract:
    """
    Build an ebook generation contract from form fields.

    This is the single entry point for all ebook contract creation in the pipeline.
    """
    cats = _detect_risk_category(topic, audience=audience)
    disclaimer_required = _needs_disclaimer(topic, audience=audience)
    disclaimer_text = (
        override_disclaimer
        if override_disclaimer
        else _build_disclaimer_text(topic)
    )

    # Build forbidden claims list based on risk categories.
    forbidden: list[str] = [
        "unsupported claims about health outcomes",
        "unsupported claims about financial results",
        "unsupported legal advice",
        "generic motivational filler without topic-specific content",
        "fake testimonials or invented case studies presented as real",
        "invented statistics or studies without sources",
    ]

    # If research was not requested, forbid research-dependent claims.
    if not research_requested:
        forbidden.extend([
            "cutting-edge research",
            "latest research",
            "scientifically proven",
            "clinically proven",
            "fact-checked",
            "thoroughly fact-checked",
            "studies show",
            "research proves",
        ])

    # Build allowed claims list.
    allowed: list[str] = [
        "general educational information",
        "common-sense practical advice",
        "commonly observed patterns (clearly labeled as such)",
        "examples clearly labeled as fictional/sample scenarios",
        "actionable steps and methods",
        "topic-specific explanations",
    ]

    # Build marketing claim limits.
    marketing_limits: list[str] = [
        "Do not claim cutting-edge, latest, or fact-checked research unless research was actually performed",
        "Do not use 'guaranteed', 'miracle', 'secret', 'effortless', or 'fast results' language",
        "Do not use pressure tactics like 'time's running out' or 'last chance'",
        "Use honest descriptors: 'practical', 'beginner-friendly', 'step-by-step', 'realistic', 'sustainable'",
    ]

    # Chapter angles by topic category.
    chapter_angles: list[str] = []
    if "fitness" in cats or "health" in cats:
        chapter_angles = [
            "muscle loss and metabolism changes after 40/50",
            "joint-friendly movement and safe exercise",
            "protein and hydration needs for this audience",
            "sleep, recovery, and energy management",
            "habit building and realistic goal setting",
            "social and emotional factors affecting health",
        ]
    elif "finance" in cats or "investing" in cats:
        chapter_angles = [
            "budgeting and spending awareness",
            "debt reduction strategies",
            "emergency fund basics",
            "investment fundamentals appropriate for beginners",
            "risk assessment and diversification",
            "long-term planning and compounding",
        ]
    elif "legal" in cats:
        chapter_angles = [
            "understanding your rights",
            "when to seek professional legal help",
            "common legal documents explained simply",
            "jurisdiction and how laws differ",
            "red flags and warning signs",
        ]

    return EbookContract(
        topic=topic,
        audience=audience,
        reader_problem=reader_problem,
        desired_transformation=desired_transformation,
        reading_level=reading_level,
        tone=tone,
        ebook_length=ebook_length,
        chapter_count=chapter_count,
        topic_category=_categorize_topic(topic),
        risk_categories=cats,
        research_requested=research_requested,
        claims_allowed=allowed,
        claims_forbidden=forbidden,
        disclaimer_required=disclaimer_required,
        disclaimer_text=disclaimer_text,
        required_chapter_angles=chapter_angles,
        worksheet_required=worksheet_required,
        worksheet_expectation=worksheet_expectation,
        marketing_claim_limits=marketing_limits,
        _is_fitness_topic="fitness" in cats,
        _is_health_topic="health" in cats,
        _is_finance_topic="finance" in cats or "investing" in cats,
        _is_legal_topic="legal" in cats,
    )


def _categorize_topic(topic: str) -> str:
    """Return a rough category label for a topic string."""
    t = topic.lower()
    if any(k in t for k in RISK_KEYWORDS["fitness"]):
        return "fitness"
    if any(k in t for k in RISK_KEYWORDS["health"]):
        return "health"
    if any(k in t for k in RISK_KEYWORDS["finance"]):
        return "finance"
    if any(k in t for k in RISK_KEYWORDS["legal"]):
        return "legal"
    if any(k in t for k in RISK_KEYWORDS["investing"]):
        return "investing"
    return "general"


def contract_to_prompt_guidance(contract: EbookContract) -> str:
    """
    Convert a contract into a paragraph of guidance to inject into AI prompts.
    This is the shared text injected into both ebook.py and product.py prompts.
    """
    lines = [
        f"TOPIC: {contract.topic}",
        f"AUDIENCE: {contract.audience}" if contract.audience else "AUDIENCE: General adult readers",
        f"TONE: {contract.tone}",
        f"READING LEVEL: {contract.reading_level}",
    ]

    # Surface the customer problem and product promise (filled from the
    # research brief) as direct product framing so the model's writing is
    # anchored to them, not only to chapter angles.
    if contract.reader_problem:
        lines.append(f"CUSTOMER PROBLEM (address throughout): {contract.reader_problem}")
    if contract.desired_transformation:
        lines.append(f"PRODUCT PROMISE (deliver this outcome): {contract.desired_transformation}")

    if contract.risk_categories:
        lines.append(f"RISK CATEGORIES: {', '.join(contract.risk_categories)}")

    if contract.disclaimer_required:
        lines.append(
            f"\nREQUIRED DISCLAIMER (must appear in the ebook):\n{contract.disclaimer_text}"
        )

    if contract.claims_forbidden:
        lines.append("\nFORBIDDEN — do not include any of the following:")
        for claim in contract.claims_forbidden:
            lines.append(f"  - {claim}")

    if not contract.research_requested:
        lines.append(
            "\nIMPORTANT: Research was NOT performed for this ebook. "
            "Do not claim 'scientifically proven', 'fact-checked', 'latest research', "
            "'cutting-edge research', or any similar phrase unless you are ONLY "
            "describing commonly known general information with no invented statistics."
        )

    if contract.required_chapter_angles:
        lines.append("\nCHAPTER ANGLES — each chapter must address at least one of these:")
        for angle in contract.required_chapter_angles:
            lines.append(f"  - {angle}")

    lines.append("\nCHAPTER CRAFT (vary structure — do NOT clone the same headings):")
    for elem in REQUIRED_CHAPTER_ELEMENTS:
        lines.append(f"  - {elem}")
    lines.append(
        "\nFORBIDDEN as repeated H3 labels across chapters "
        "(never use the same generic label in every chapter):"
    )
    for phrase in FORBIDDEN_REPEATED_HEADINGS:
        lines.append(f"  - '{phrase}'")
    lines.append(
        "Use descriptive H3 labels tied to the chapter content "
        "(e.g. 'A Calmer Way to End Tablet Time', 'The Three-Question Content Check')."
    )
    lines.append("Do not duplicate 'Chapter N' inside a chapter title that already has a number.")

    if contract.research_requested or contract.required_chapter_angles:
        lines.append(
            "\nUse the user's selected research/niche angles. "
            "Do not invent studies, statistics, expert quotes, or medical claims. "
            "If a fact came from research notes, keep the source name for a References section."
        )

    lines.append("\nDO NOT USE generic filler such as:")
    for phrase in sorted(GENERIC_FILLER_PHRASES):
        lines.append(f"  - '{phrase}'")

    lines.append("\nNEVER include fake statistics, fake studies, or fake testimonials.")
    lines.append("If you use example scenarios, label them clearly: 'Example scenario:', 'Sample situation:', or 'Imagine a reader named...'")

    if contract.worksheet_required:
        lines.append(f"\nWORKSHEET REQUIREMENT: {contract.worksheet_expectation}")

    lines.append("\nKeep all claims honest, specific, and appropriate for the audience.")

    return "\n".join(lines)
