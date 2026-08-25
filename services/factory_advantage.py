"""Factory Market Advantage — transparent research scoring and report assembly.

This is Factory's original research upgrade. It is not a clone of any third-party
scoring product. Numeric scores are computed here from evidence, never from a
hidden model-only number.

Factory Advantage Score (0–100) = sum of:
  Demand                     0–20
  Competition Opportunity    0–20
  Buyer Urgency              0–15
  Monetization Potential     0–15
  Differentiation Potential  0–15
  Production Fit             0–10
  Evidence Confidence        0–5

Unverified search volume, sales, revenue, BSR, review counts, and prices are
recorded as "Not verified" and do not add points. Missing evidence lowers
Evidence Confidence.

Recommendation bands (applied after the total is computed):
  Insufficient Evidence          evidence_confidence < 2, or total < 30 with 4+ missing items
  Strong Opportunity             total >= 75 and evidence_confidence >= 3
  Promising—Needs Positioning    total >= 55
  Test Before Building           total >= 40
  Weak Opportunity               otherwise
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from services.book_sales_estimate import NOT_VERIFIED, estimate_book_sales
from services.quality.artifact_state import ArtifactState

DISCLAIMER = (
    "Scores and revenue estimates are research indicators, "
    "not guaranteed sales or earnings."
)

WORKFLOW_LABEL = "Factory Market Advantage"
WORKFLOW_TAGLINE = "Find it. Prove it—before you build it."

COMPONENT_CAPS = {
    "demand": 20,
    "competition_opportunity": 20,
    "buyer_urgency": 15,
    "monetization_potential": 15,
    "differentiation_potential": 15,
    "production_fit": 10,
    "evidence_confidence": 5,
}

# Required in-Factory labels mapped onto the documented 7-component formula.
# Buyer Urgency stays visible so the published formula is not hidden.
COMPONENT_DISPLAY_LABELS = {
    "demand": "Demand",
    "competition_opportunity": "Competition",
    "buyer_urgency": "Buyer Urgency",
    "monetization_potential": "Profit Potential",
    "differentiation_potential": "Differentiation",
    "production_fit": "Ease of Creation",
    "evidence_confidence": "Evidence Confidence",
}

INSUFFICIENT_EVIDENCE = "Insufficient evidence"
USER_DECISION_BUILD = "BUILD"
USER_DECISION_IMPROVE = "IMPROVE THE IDEA"
USER_DECISION_AVOID = "AVOID"
RECOMMENDATION_TO_DECISION = {
    "Strong Opportunity": USER_DECISION_BUILD,
    "Promising—Needs Positioning": USER_DECISION_IMPROVE,
    "Test Before Building": USER_DECISION_IMPROVE,
    "Weak Opportunity": USER_DECISION_AVOID,
    "Insufficient Evidence": USER_DECISION_AVOID,
}

_MARKETPLACE_HOSTS = (
    ("amazon.", "Amazon"),
    ("amzn.", "Amazon"),
    ("etsy.", "Etsy"),
    ("gumroad.", "Gumroad"),
    ("teacherspayteachers.", "Teachers Pay Teachers"),
    ("tpt.com", "Teachers Pay Teachers"),
    ("shopify.", "Shopify"),
)
_TREND_CLAIM_RE = re.compile(
    r"\b(?:hot |currently |really )?(?:trending|trend(?:s)?)\b",
    re.I,
)
_PROMOTIONAL_TITLE_RE = re.compile(
    r"(?i)(?:dominate|passive income|top\s+\d+\s+products|must[- ]have|"
    r"click here|limited time|make\s+\$?\d|secret to selling)"
)
_UNVERIFIED_EARNINGS_RE = re.compile(
    r"(?i)(?:makes?|earn(?:s|ing)?|profit(?:s)?|revenue)\s*(?:of\s*)?"
    r"\$?\d[\d,]*(?:\s*[-–—to]+\s*\$?\d[\d,]*)?\s*(?:per|/)\s*month"
)
_SOCIAL_HOSTS = (
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "instagram.com",
    "pinterest.com",
    "facebook.com",
    "twitter.com",
    "x.com",
)
_TREND_HOSTS = ("trends.google.", "google.com/trends")
_INDUSTRY_HOSTS = (
    "statista.com",
    "pewresearch.org",
    "census.gov",
    "ibisworld.com",
    "nielsen.com",
    "oecd.org",
    "eia.gov",
    "bls.gov",
)
_RETAIL_HOSTS = ("walmart.", "target.com", "ebay.", "bestbuy.")
EVIDENCE_TYPES = (
    "Market trend",
    "Buyer demand",
    "Competition",
    "Pricing signal",
    "Marketplace signal",
    "Risk",
)
SOURCE_CLASSES = (
    "Marketplace",
    "Search trend",
    "Industry report",
    "Retail listing",
    "Social signal",
    "Publisher article",
)
CUSTOMER_CONFIDENCE = ("Strong", "Moderate", "Limited")

SALES_PLATFORMS = (
    "Amazon KDP",
    "Etsy",
    "Gumroad",
    "Shopify",
    "Own website",
    "Not sure",
)

EXPERTISE_LEVELS = ("Beginner", "Some experience", "Experienced")

DEPTH_QUICK = "Quick Check"
DEPTH_FULL = "Full Validation"
DEPTH_OPTIONS = (DEPTH_QUICK, DEPTH_FULL)

# Labels from the Factory product-type registry (static/js/app.js PRODUCT_TYPES).
# Hidden builders stay listed so research can name them, but handoff will not
# silently fall back to Ebook.
REGISTRY_PRODUCT_TYPES = (
    "Ebook",
    "Coloring Book",
    "Word Search Book",
    "Crossword Puzzle Book",
    "Math Worksheet",
    "Spelling Worksheet",
    "Flip Book",
    "Cover Design",
    "Planner",
    "Marketing Kit",
    "Workbook",
    "Checklist",
    "Not Sure Yet",
)

ACTIVE_BUILDERS = {
    "ebook": "ebook",
    "coloring book": "coloring_book",
    "word search book": "word_search",
    "crossword puzzle book": "crossword",
    "math worksheet": "math_worksheet",
    "faith planner": "faith_planner",
    "budget planner": "budget_planner",
}

HIDDEN_BUILDERS = {
    "spelling worksheet": "spelling_worksheet",
    "flip book": "flip_book",
    "cover design": "cover_design",
    "planner": "planner",
    "marketing kit": "marketing_kit",
}

# Workbook/Checklist are catalog aliases that already route to the Ebook Builder.
EBOOK_ALIASES = {
    "workbook": "ebook",
    "checklist": "ebook",
    "guide": "ebook",
}

UNVERIFIED_METRIC_KEYS = (
    "search_volume",
    "monthly_searches",
    "bsr",
    "bestseller_rank",
    "best_seller_rank",
    "revenue",
    "monthly_sales",
    "unit_sales",
    "review_count",
    "reviews",
    "estimated_sales",
    "estimated_revenue",
)

_URGENT_TERMS = (
    "urgent",
    "quickly",
    "deadline",
    "overwhelm",
    "overwhelmed",
    "anxious",
    "anxiety",
    "struggling",
    "stuck",
    "need",
    "help kids",
    "last minute",
    "time-poor",
    "busy",
)


def utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _clamp(value: int, cap: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 0
    return max(0, min(cap, n))


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _clean(value).lower()


def source_website(url: str) -> str:
    host = (urlparse(_clean(url)).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def marketplace_from_url(url: str) -> str:
    host = source_website(url)
    if not host:
        return ""
    for needle, label in _MARKETPLACE_HOSTS:
        if host == needle.rstrip(".") or needle in host:
            return label
    return ""


def is_youtube_url(url: str) -> bool:
    host = source_website(url)
    return host in {"youtube.com", "youtu.be"} or host.endswith(".youtube.com")


def map_user_decision(recommendation: str) -> str:
    return RECOMMENDATION_TO_DECISION.get(_clean(recommendation), USER_DECISION_AVOID)


# Customer-facing labels. Scoring bands stay unchanged; this is display mapping only.
PLAIN_OPPORTUNITY_LABELS = {
    "Strong Opportunity": "Promising",
    "Promising—Needs Positioning": "Needs Improvement",
    "Test Before Building": "Needs Improvement",
    "Weak Opportunity": "Avoid",
    "Insufficient Evidence": "Insufficient Evidence",
}
CUSTOMER_COMPONENT_SIGNALS = (
    ("demand", "Demand"),
    ("competition_opportunity", "Competition"),
    ("buyer_urgency", "Customer Need"),
    ("monetization_potential", "Profit Evidence"),
    ("differentiation_potential", "Ability to Stand Out"),
)
HOW_DETERMINED_PLAIN = (
    "The Factory looked at demand signals, competition, the customer problem, "
    "ability to differentiate, possible monetization, production fit, and the "
    "quality of available evidence."
)
MVP_STARTERS = {
    "Coloring Book": (
        "Start with: a themed coloring book for {audience} titled {idea}, "
        "with a clear hero or setting and simple page-by-page scenes."
    ),
    "Crossword Puzzle Book": (
        "Start with: a crossword book for {audience} built around {idea}, "
        "with themed clues and an answer key."
    ),
    "Word Search Book": (
        "Start with: a word-search pack for {audience} using the {idea} word list "
        "and a simple difficulty progression."
    ),
    "Ebook": "Start with: a short ebook for {audience} that walks through {problem}.",
    "Workbook": "Start with: a short workbook for {audience} that practices {problem}.",
    "Checklist": "Start with: a practical checklist for {audience} covering {idea}.",
    "Math Worksheet": (
        "Start with: a printable practice pack for {audience} focused on {idea}, "
        "with clear problems and answers."
    ),
    "Planner": "Start with: a simple planner for {audience} organized around {idea}.",
    "Faith Planner": (
        "Start with: an undated devotional planner for {audience} built around "
        "{idea}, with a reading plan, prayer log, and reflection pages."
    ),
    "Budget Planner": (
        "Start with: an undated budget planner for {audience} built around "
        "{idea}, with monthly worksheets, an expense log, and a debt tracker."
    ),
}


def plain_opportunity_label(recommendation: str, user_decision: str | None = None) -> str:
    reco = _clean(recommendation)
    if reco in PLAIN_OPPORTUNITY_LABELS:
        return PLAIN_OPPORTUNITY_LABELS[reco]
    decision = _clean(user_decision) or map_user_decision(reco)
    if "insufficient" in reco.lower():
        return "Insufficient Evidence"
    if decision == USER_DECISION_BUILD:
        return "Promising"
    if decision == USER_DECISION_IMPROVE:
        return "Needs Improvement"
    return "Avoid"


def plain_component_signal(row: dict | None) -> str:
    """Translate a numeric component into a customer label. Does not rescore."""
    row = row if isinstance(row, dict) else {}
    try:
        score = int(row.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    try:
        cap = int(row.get("max") or 1) or 1
    except (TypeError, ValueError):
        cap = 1
    missing = [m for m in (row.get("missing_evidence") or []) if _clean(str(m))]
    ratio = score / cap
    if ratio >= 0.7:
        return "Good Signal"
    if missing and ratio < 0.5:
        return "More Research Needed"
    if ratio >= 0.45:
        return "Mixed Signal"
    if missing:
        return "More Research Needed"
    return "Weak Signal"


def reject_unsupported_trend_language(text: str) -> str:
    """General articles may not be labeled trending. Replace unsupported claims."""
    value = _clean(text)
    if not value or not _TREND_CLAIM_RE.search(value):
        return value
    return _TREND_CLAIM_RE.sub("discussed", value)


def listing_from_source(raw: dict, researched_at: str | None = None) -> dict | None:
    """Marketplace listing row. Never invents price, rating, reviews, or BSR."""
    src = raw if isinstance(raw, dict) else {}
    url = _clean(src.get("url") or src.get("listing_url"))
    market = _clean(src.get("marketplace")) or marketplace_from_url(url)
    if not market or is_youtube_url(url):
        return None
    checked = _clean(src.get("date_checked") or src.get("access_date")) or researched_at or utc_today()
    price_ok = bool(src.get("price_verified") and _clean(src.get("price")))
    rating_ok = bool(src.get("rating_verified") and _clean(src.get("rating")))
    reviews_ok = bool(src.get("reviews_verified") and _clean(src.get("reviews") or src.get("review_count")))
    bsr_ok = bool(src.get("bsr_verified") and _clean(src.get("bsr") or src.get("bestseller_rank")))
    title = _clean(src.get("name") or src.get("title")) or "Listing"
    if _PROMOTIONAL_TITLE_RE.search(title) or has_unverified_earnings_claim(src):
        title = f"{market} listing"
    return {
        "title": title,
        "name": title,
        "marketplace": market,
        "price": _clean(src.get("price")) if price_ok else NOT_VERIFIED,
        "rating": _clean(src.get("rating")) if rating_ok else NOT_VERIFIED,
        "reviews": _clean(src.get("reviews") or src.get("review_count")) if reviews_ok else NOT_VERIFIED,
        "bsr": _clean(src.get("bsr") or src.get("bestseller_rank")) if bsr_ok else NOT_VERIFIED,
        "listing_url": url,
        "url": url,
        "date_checked": checked,
        "access_date": checked,
        "angle": _clean(src.get("angle") or src.get("excerpt")),
    }


def youtube_from_source(raw: dict, researched_at: str | None = None) -> dict | None:
    src = raw if isinstance(raw, dict) else {}
    url = _clean(src.get("url"))
    if not is_youtube_url(url):
        return None
    views_ok = bool(src.get("views_verified") and _clean(src.get("views")))
    title = _clean(src.get("title")) or "YouTube video"
    if _PROMOTIONAL_TITLE_RE.search(title) or has_unverified_earnings_claim(src):
        title = "Public video signal"
    return {
        "title": title,
        "channel": _clean(src.get("channel")) or NOT_VERIFIED,
        "date": _clean(src.get("published_at") or src.get("publication_date")) or NOT_VERIFIED,
        "views": _clean(src.get("views")) if views_ok else NOT_VERIFIED,
        "url": url,
        "excerpt": _clean(src.get("excerpt") or src.get("content"))[:240],
        "access_date": _clean(src.get("access_date")) or researched_at or utc_today(),
    }


def _source_blob(src: dict) -> str:
    return " ".join(
        _clean(src.get(key))
        for key in ("title", "excerpt", "content", "snippet", "angle")
        if _clean(src.get(key))
    )


def is_promotional_source(src: dict) -> bool:
    blob = _source_blob(src if isinstance(src, dict) else {})
    title = _clean((src or {}).get("title"))
    return bool(_PROMOTIONAL_TITLE_RE.search(title) or _UNVERIFIED_EARNINGS_RE.search(blob))


def has_unverified_earnings_claim(src: dict) -> bool:
    return bool(_UNVERIFIED_EARNINGS_RE.search(_source_blob(src if isinstance(src, dict) else {})))


def source_class_for(src: dict) -> str:
    url = _clean((src or {}).get("url") or (src or {}).get("listing_url"))
    host = source_website(url)
    path = (urlparse(url).path or "").lower()
    if marketplace_from_url(url):
        return "Marketplace"
    if any(host == h or host.endswith("." + h) or h in host for h in _SOCIAL_HOSTS) or is_youtube_url(url):
        return "Social signal"
    if any(needle in host or needle in url.lower() for needle in _TREND_HOSTS) or "trends" in path:
        return "Search trend"
    if any(host == h or host.endswith("." + h) for h in _INDUSTRY_HOSTS):
        return "Industry report"
    if any(needle in host for needle in _RETAIL_HOSTS):
        return "Retail listing"
    return "Publisher article"


def evidence_type_for(src: dict) -> str:
    blob = _source_blob(src if isinstance(src, dict) else {}).lower()
    cls = source_class_for(src if isinstance(src, dict) else {})
    if any(term in blob for term in ("risk", "saturat", "complaint", "warning", "oversupply")):
        return "Risk"
    if any(term in blob for term in ("price", "pricing", "$", "usd")) and cls in {"Marketplace", "Retail listing"}:
        return "Pricing signal"
    if cls == "Marketplace":
        return "Marketplace signal"
    if cls == "Search trend" or "search interest" in blob:
        return "Market trend"
    if any(term in blob for term in ("compet", "crowded", "similar listing", "many sellers")):
        return "Competition"
    if any(term in blob for term in ("price", "pricing", "bundle")):
        return "Pricing signal"
    if cls == "Social signal":
        return "Buyer demand"
    return "Buyer demand"


def customer_confidence_for(src: dict) -> str:
    if is_promotional_source(src) or has_unverified_earnings_claim(src):
        return "Limited"
    cls = source_class_for(src)
    raw = _lower((src or {}).get("confidence"))
    if cls in {"Marketplace", "Retail listing", "Search trend", "Industry report"}:
        return "Strong" if raw != "low" else "Moderate"
    if raw == "high":
        return "Moderate"
    if raw == "low":
        return "Limited"
    return "Moderate"


def factory_written_summary(src: dict) -> str:
    """Short Factory-written fact. Never reuse a promotional headline as the card."""
    excerpt = reject_unsupported_trend_language(
        _clean((src or {}).get("excerpt") or (src or {}).get("content") or (src or {}).get("snippet"))
    )
    if has_unverified_earnings_claim(src):
        excerpt = _UNVERIFIED_EARNINGS_RE.sub("an unverified earnings range", excerpt)
        excerpt = (
            "An unverified promotional earnings claim was found. "
            "Factory does not treat it as a sales fact. "
            + excerpt
        )
    excerpt = re.sub(r"\s+", " ", excerpt).strip()
    if excerpt:
        return excerpt[:220]
    return (
        f"Factory recorded a {evidence_type_for(src).lower()} "
        f"from a public {source_class_for(src).lower()}."
    )


def score_effect_text(src: dict, score: dict | None = None) -> str:
    score = score or {}
    if customer_confidence_for(src) == "Limited" or has_unverified_earnings_claim(src):
        return (
            "Treated as weak supporting evidence only. "
            "It did not raise the Factory Advantage Score as a verified fact."
        )
    etype = evidence_type_for(src)
    key = {
        "Buyer demand": "demand",
        "Market trend": "demand",
        "Competition": "competition_opportunity",
        "Marketplace signal": "competition_opportunity",
        "Pricing signal": "monetization_potential",
        "Risk": "evidence_confidence",
    }.get(etype, "demand")
    row = ((score.get("components") or {}).get(key) or {})
    label = row.get("display_label") or COMPONENT_DISPLAY_LABELS.get(key) or etype
    if row.get("score") is not None:
        return (
            f"Supported the {label} component of the Factory Advantage Score "
            f"({row.get('score')}/{row.get('max')})."
        )
    reco = score.get("recommendation") or "Insufficient Evidence"
    return f"Informed the Factory recommendation: {reco}."


def source_quality_rank(src: dict) -> int:
    cls = source_class_for(src)
    ranks = {
        "Marketplace": 1,
        "Retail listing": 1,
        "Search trend": 2,
        "Industry report": 3,
        "Social signal": 4,
        "Publisher article": 5,
    }
    rank = ranks.get(cls, 5)
    if is_promotional_source(src) or has_unverified_earnings_claim(src):
        rank += 8
    return rank


def _material_sources(sources: list[dict] | None) -> list[dict]:
    """Sources that materially support the decision. Do not pad."""
    chosen = []
    seen = set()
    ranked = sorted(
        [s for s in (sources or []) if isinstance(s, dict) and (s.get("url") or s.get("title") or s.get("excerpt"))],
        key=source_quality_rank,
    )
    for src in ranked:
        summary = factory_written_summary(src)
        domain = _clean(src.get("website")) or source_website(src.get("url") or src.get("listing_url") or "")
        key = (domain, summary[:80].lower())
        if key in seen:
            continue
        if is_promotional_source(src) and not _clean(src.get("excerpt") or src.get("content")):
            continue
        if has_unverified_earnings_claim(src) and not _clean(src.get("excerpt") or src.get("content")):
            continue
        seen.add(key)
        chosen.append(src)
    return chosen


def _sources_for_score(sources: list[dict] | None) -> list[dict]:
    """URL sources that may affect the score. Promotional earnings claims do not count as facts."""
    return [
        s
        for s in (sources or [])
        if isinstance(s, dict) and s.get("url") and not has_unverified_earnings_claim(s)
    ]


def customer_facing_card(src: dict, score: dict | None = None) -> dict:
    pub = _clean((src or {}).get("publication_date") or (src or {}).get("published_at"))
    accessed = _clean((src or {}).get("access_date") or (src or {}).get("date_checked"))
    card = {
        "evidence_type": evidence_type_for(src),
        "fact": factory_written_summary(src),
        "score_effect": score_effect_text(src, score),
        "source_class": source_class_for(src),
        "confidence": customer_confidence_for(src),
    }
    if pub and pub != accessed:
        card["evidence_date"] = pub
    elif pub:
        card["evidence_date"] = pub
    return card


def how_we_know_item(src: dict) -> dict:
    pub = _clean((src or {}).get("publication_date") or (src or {}).get("published_at"))
    accessed = _clean((src or {}).get("access_date") or (src or {}).get("date_checked")) or utc_today()
    domain = _clean((src or {}).get("website")) or source_website(
        (src or {}).get("url") or (src or {}).get("listing_url") or ""
    )
    item = {
        "summary": factory_written_summary(src),
        "source_domain": domain,
        "accessed": accessed,
        "supported_claim": factory_written_summary(src),
        "relevance": (
            f"This {source_class_for(src).lower()} was used as a {evidence_type_for(src).lower()} "
            "because it describes a public market signal for the idea under review."
        ),
    }
    if pub:
        item["publication_date"] = pub
    return item


def internal_evidence_row(src: dict, research_result: str = "") -> dict:
    url = _clean((src or {}).get("url") or (src or {}).get("listing_url"))
    return {
        "title": _clean((src or {}).get("title")) or "Untitled",
        "url": url,
        "domain": _clean((src or {}).get("website")) or source_website(url),
        "retrieval_date": _clean((src or {}).get("access_date")) or utc_today(),
        "publication_date": _clean((src or {}).get("publication_date") or (src or {}).get("published_at")),
        "supported_claim": factory_written_summary(src),
        "research_result": research_result or factory_written_summary(src),
        "source_class": source_class_for(src),
        "promotional": is_promotional_source(src),
    }


def build_evidence_used(
    sources: list[dict] | None,
    *,
    score: dict | None = None,
    evidence: dict | None = None,
) -> dict:
    del evidence
    material = _material_sources(sources)
    cards = [customer_facing_card(src, score) for src in material]
    count = len(cards)
    if count == 1:
        intro = "Factory reviewed 1 public market signal and summarized the findings below."
    else:
        intro = f"Factory reviewed {count} public market signals and summarized the findings below."
    return {
        "title": "Evidence Used",
        "intro": intro,
        "count": count,
        "cards": cards,
    }


def build_how_we_know(sources: list[dict] | None, *, score: dict | None = None) -> dict:
    del score
    items = [how_we_know_item(src) for src in _material_sources(sources)]
    return {
        "title": "How We Know",
        "items": items,
    }


def build_internal_evidence_record(
    sources: list[dict] | None,
    *,
    research_result: str = "",
) -> list[dict]:
    rows = []
    for src in sources or []:
        if not isinstance(src, dict):
            continue
        if not (src.get("url") or src.get("title") or src.get("excerpt")):
            continue
        rows.append(internal_evidence_row(src, research_result=research_result))
    return rows


def compact_evidence_summary(opp: dict, score: dict | None = None) -> dict:
    reco = (score or {}).get("recommendation") or "Insufficient Evidence"
    sources = (opp or {}).get("sources") or []
    used = build_evidence_used(sources, score=score, evidence=(opp or {}).get("evidence") or {})
    know = build_how_we_know(sources, score=score)
    return {
        "product_idea": _clean((opp or {}).get("product_idea")),
        "target_customer": _clean((opp or {}).get("target_audience")),
        "customer_problem": _clean((opp or {}).get("customer_problem")),
        "product_format": _clean((opp or {}).get("product_type")),
        "trend": INSUFFICIENT_EVIDENCE,
        "competition": _clean((opp or {}).get("competition")) or NOT_VERIFIED,
        "price_range": _clean((opp or {}).get("price_range")) or NOT_VERIFIED,
        "recommendation": reco,
        "user_decision": map_user_decision(reco),
        "evidence_used": used,
        "how_we_know": know,
        "note": "Factory summarized the available public signals inside the Factory.",
    }


def normalize_product_type(product_type: str) -> str:
    raw = _clean(product_type)
    if not raw:
        return "Not Sure Yet"
    for label in REGISTRY_PRODUCT_TYPES:
        if label.lower() == raw.lower():
            return label
    return raw


def resolve_factory_builder(product_type: str) -> dict:
    """Map a research/plan product type to a Factory builder.

    Coloring Book → coloring_book, Crossword → crossword, Ebook → ebook.
    Never silently rewrite coloring/crossword/word-search to ebook.
    """
    pt = _lower(product_type)
    if not pt or pt == "not sure yet":
        return {"status": "unknown", "factory_id": None, "label": product_type or ""}

    for label, factory_id in ACTIVE_BUILDERS.items():
        if pt == label:
            return {"status": "active", "factory_id": factory_id, "label": normalize_product_type(product_type)}
    for label, factory_id in HIDDEN_BUILDERS.items():
        if pt == label:
            return {"status": "hidden", "factory_id": factory_id, "label": normalize_product_type(product_type)}

    # Heuristics: coloring / crossword / word search MUST win before book→ebook.
    if "color" in pt:
        return {"status": "active", "factory_id": "coloring_book", "label": "Coloring Book"}
    if "word search" in pt:
        return {"status": "active", "factory_id": "word_search", "label": "Word Search Book"}
    if "crossword" in pt:
        return {"status": "active", "factory_id": "crossword", "label": "Crossword Puzzle Book"}
    if "spelling" in pt:
        return {"status": "hidden", "factory_id": "spelling_worksheet", "label": "Spelling Worksheet"}
    if "math" in pt or "worksheet" in pt:
        return {"status": "active", "factory_id": "math_worksheet", "label": "Math Worksheet"}
    if "flip" in pt:
        return {"status": "hidden", "factory_id": "flip_book", "label": "Flip Book"}
    if "cover" in pt:
        return {"status": "hidden", "factory_id": "cover_design", "label": "Cover Design"}
    # Faith and Budget planners are shipped builders; the generic "planner"
    # remains hidden, so the specific match has to be tested first.
    if "faith" in pt and "planner" in pt:
        return {"status": "active", "factory_id": "faith_planner", "label": "Faith Planner"}
    if ("budget" in pt or "money" in pt or "finance" in pt) and "planner" in pt:
        return {"status": "active", "factory_id": "budget_planner", "label": "Budget Planner"}
    if "planner" in pt or "planning" in pt:
        return {"status": "hidden", "factory_id": "planner", "label": "Planner"}
    if "marketing" in pt:
        return {"status": "hidden", "factory_id": "marketing_kit", "label": "Marketing Kit"}
    if pt in EBOOK_ALIASES or pt == "ebook":
        return {"status": "active", "factory_id": "ebook", "label": "Ebook"}
    if "book" in pt or "guide" in pt:
        return {"status": "active", "factory_id": "ebook", "label": "Ebook"}
    return {"status": "unknown", "factory_id": None, "label": product_type}


def coerce_selected_product_type(opportunities: list[dict], product_type: str) -> list[dict]:
    """Keep the user-selected Factory product type on every opportunity."""
    selected = normalize_product_type(product_type)
    if not selected or selected == "Not Sure Yet":
        return opportunities
    cleaned = []
    for item in opportunities:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row["product_type"] = selected
        cleaned.append(row)
    return cleaned


def normalize_source(raw: dict, access_date: str | None = None) -> dict:
    row = raw if isinstance(raw, dict) else {}
    url = _clean(row.get("url"))
    excerpt = _clean(row.get("excerpt") or row.get("content") or row.get("snippet"))
    confidence = _clean(row.get("confidence")) or ("medium" if url else "low")
    publication = _clean(row.get("publication_date") or row.get("published_at") or row.get("published"))
    return {
        "title": _clean(row.get("title")) or "Untitled",
        "url": url,
        "website": _clean(row.get("website")) or source_website(url),
        "access_date": _clean(row.get("access_date")) or access_date or utc_today(),
        "publication_date": publication,
        "excerpt": excerpt[:500],
        "confidence": confidence,
    }


def classify_evidence(
    *,
    sources: list[dict],
    inputs: dict,
    live: bool,
    ai_notes: list[str] | None = None,
    unverified_metrics: list[str] | None = None,
) -> dict:
    """Split evidence into Verified Facts / Calculated Estimates / AI / Missing."""
    sourced = [normalize_source(s) for s in (sources or []) if isinstance(s, dict)]
    unverified = list(unverified_metrics or [])
    for key in UNVERIFIED_METRIC_KEYS:
        if key not in unverified:
            unverified.append(key.replace("_", " "))

    verified_facts = []
    for src in sourced:
        if not (src["url"] and src["excerpt"]):
            continue
        if has_unverified_earnings_claim(src):
            continue
        verified_facts.append(
            {
                "claim": src["excerpt"][:240],
                "source_title": src["title"],
                "url": src["url"],
                "access_date": src["access_date"],
                "confidence": src["confidence"],
            }
        )

    missing = [
        "Search volume (Not verified)",
        "Best-seller rank / BSR (Not verified)",
        "Unit sales (Not verified)",
        "Revenue (Not verified)",
        "Review counts (Not verified)",
    ]
    if not sourced:
        missing.insert(0, "Live web sources")
    if not _clean(inputs.get("customer_problem")):
        missing.append("Customer problem detail")
    if not _clean(inputs.get("target_price")):
        missing.append("Verified market price")
    if not live:
        missing.append("Live web research session")

    calculated = [
        {
            "label": "Factory Advantage Score",
            "note": "Calculated from the documented component formula; not a sales forecast.",
        }
    ]
    sales = estimate_book_sales()
    calculated.append(
        {
            "label": "Book sales estimate",
            "value": NOT_VERIFIED,
            "note": sales["reason"],
        }
    )

    return {
        "sources": sourced,
        "verified_facts": verified_facts,
        "calculated_estimates": calculated,
        "ai_interpretation": [str(n) for n in (ai_notes or []) if str(n).strip()],
        "missing_information": missing,
        "unverified_metrics": sorted(set(unverified)),
        "live": bool(live),
    }


def _component(
    key: str,
    score: int,
    explanation: str,
    evidence: list[str],
    missing: list[str],
    researched_at: str,
) -> dict:
    cap = COMPONENT_CAPS[key]
    return {
        "key": key,
        "label": key.replace("_", " ").title(),
        "display_label": COMPONENT_DISPLAY_LABELS.get(key) or key.replace("_", " ").title(),
        "score": _clamp(score, cap),
        "max": cap,
        "explanation": explanation,
        "evidence": evidence,
        "missing_evidence": missing,
        "researched_at": researched_at,
    }


def score_demand(inputs: dict, evidence: dict, researched_at: str) -> dict:
    """Demand 0–20. Source mentions and stated audience/problem only. No search volume."""
    sources = evidence.get("sources") or []
    with_url = _sources_for_score(sources)
    topic = _clean(inputs.get("topic") or inputs.get("niche") or inputs.get("interest"))
    audience = _clean(inputs.get("audience"))
    problem = _clean(inputs.get("customer_problem"))
    score = 0
    ev = []
    missing = []
    if topic and audience:
        score += 6
        ev.append("Topic and audience were provided by the user.")
    elif topic:
        score += 3
        ev.append("A topic was provided.")
        missing.append("Target audience")
    else:
        missing.append("Topic / idea")
    if problem:
        score += 6
        ev.append("A customer problem was stated.")
    else:
        missing.append("Customer problem")
    if len(with_url) >= 3:
        score += 8
        ev.append(f"{len(with_url)} sourced excerpts mention market context.")
    elif len(with_url) >= 1:
        score += 5
        ev.append("At least one sourced excerpt is available.")
        missing.append("Additional independent demand sources")
    else:
        missing.append("Verified demand sources (search volume is Not verified)")
    if "search volume" in " ".join(evidence.get("unverified_metrics") or []).lower():
        missing.append("Search volume (Not verified) — not scored")
    return _component("demand", score, "Demand uses stated audience/problem and sourced mentions only. Search volume is never invented.", ev, missing, researched_at)


def score_competition(inputs: dict, evidence: dict, researched_at: str) -> dict:
    """Competition Opportunity 0–20. Unverified competitor stats do not add points."""
    del inputs
    level = _lower(evidence.get("competition_level"))
    verified = bool(evidence.get("competition_verified"))
    gaps = int(evidence.get("differentiation_count") or 0)
    ev = []
    missing = []
    if not verified:
        missing.append("Verified competitor listings, BSR, and review counts (Not verified)")
        score = 6
        ev.append("Competition is treated as unknown. No BSR or review counts were verified.")
    elif level == "low":
        score = 18
        ev.append("Verified sources describe relatively open competition.")
    elif level == "medium":
        score = 12
        ev.append("Verified sources describe moderate competition.")
        if gaps:
            score = min(16, score + min(4, gaps))
            ev.append("Differentiation gaps increase opportunity inside a moderate field.")
    elif level == "high":
        score = 4
        ev.append("Verified sources describe crowded competition.")
        if gaps:
            score = 8
            ev.append("A stated gap still creates a narrow opening.")
    else:
        score = 6
        missing.append("Competition level")
        ev.append("Competition level was not classified from verified sources.")
    return _component(
        "competition_opportunity",
        score,
        "Competition opportunity rewards verified openness or a documented gap. BSR and review counts are never fabricated.",
        ev,
        missing,
        researched_at,
    )


def score_urgency(inputs: dict, evidence: dict, researched_at: str) -> dict:
    problem = _lower(inputs.get("customer_problem"))
    ev = []
    missing = []
    score = 0
    if any(term in problem for term in _URGENT_TERMS):
        score += 8
        ev.append("The stated problem includes urgency or pain language.")
    elif problem:
        score += 4
        ev.append("A customer problem is stated without strong urgency language.")
        missing.append("Urgency / time-sensitivity evidence")
    else:
        missing.append("Customer problem")
    if evidence.get("repeat_or_seasonal"):
        score += 4
        ev.append("Repeat or seasonal demand was noted in research notes.")
    else:
        missing.append("Repeat-purchase or seasonal evidence")
    if evidence.get("live") and (evidence.get("sources") or []):
        score += 3
        ev.append("Live sources were available to support the problem framing.")
    return _component("buyer_urgency", score, "Urgency is scored from the stated problem and sourced timing signals, not from invented search trends.", ev, missing, researched_at)


def score_monetization(inputs: dict, evidence: dict, researched_at: str) -> dict:
    price = _clean(inputs.get("target_price"))
    platform = _clean(inputs.get("sales_platform"))
    product_type = normalize_product_type(inputs.get("product_type") or "")
    ev = []
    missing = []
    score = 0
    if price:
        score += 6
        ev.append(f"User-stated target price: {price} (not a verified market comp).")
    else:
        missing.append("Verified market price (Not verified)")
    if platform and platform.lower() not in {"", "not sure"}:
        score += 5
        ev.append(f"Intended sales platform: {platform}.")
    else:
        missing.append("Sales platform")
    builder = resolve_factory_builder(product_type)
    if builder["status"] == "active":
        score += 4
        ev.append(f"{product_type} can be produced in Factory.")
    elif product_type and product_type != "Not Sure Yet":
        score += 2
        ev.append(f"{product_type} is named but the public builder may not be ready.")
    else:
        missing.append("Product type")
    # Invented revenue never scores.
    missing.append("Revenue / unit sales (Not verified)")
    del evidence
    return _component(
        "monetization_potential",
        score,
        "Monetization uses platform fit and user-stated price only. Revenue and BSR are Not verified.",
        ev,
        missing,
        researched_at,
    )


def score_differentiation(inputs: dict, evidence: dict, researched_at: str) -> dict:
    problem = _clean(inputs.get("customer_problem"))
    gaps = int(evidence.get("differentiation_count") or 0)
    ev = []
    missing = []
    score = 0
    if problem:
        score += 8
        ev.append("A specific customer problem can anchor a distinct angle.")
    else:
        missing.append("Customer problem / unique angle")
    if gaps >= 3:
        score += 7
        ev.append("Three original differentiation opportunities were documented.")
    elif gaps:
        score += 4
        ev.append("At least one differentiation angle was documented.")
        missing.append("Three original differentiation opportunities")
    else:
        missing.append("Documented differentiation gaps vs competitors")
    return _component(
        "differentiation_potential",
        score,
        "Differentiation is scored from a stated problem and documented original angles, not from competitor review inventing.",
        ev,
        missing,
        researched_at,
    )


def score_production_fit(inputs: dict, researched_at: str) -> dict:
    product_type = normalize_product_type(inputs.get("product_type") or "")
    expertise = _clean(inputs.get("expertise"))
    builder = resolve_factory_builder(product_type)
    ev = []
    missing = []
    score = 0
    if builder["status"] == "active":
        score += 6
        ev.append(f"{product_type} maps to the {builder['factory_id']} builder.")
    elif builder["status"] == "hidden":
        score += 2
        ev.append(f"{product_type} exists in the registry but is not a public builder yet.")
        missing.append("Public builder for this product type")
    else:
        score += 1
        missing.append("Recognized Factory product type")
    if expertise:
        score += 4
        ev.append(f"Creator experience noted: {expertise}.")
    else:
        missing.append("Creator experience / expertise")
    return _component(
        "production_fit",
        score,
        "Production fit is whether Factory can actually build this product type for this creator.",
        ev,
        missing,
        researched_at,
    )


def score_evidence_confidence(evidence: dict, researched_at: str) -> dict:
    sources = evidence.get("sources") or []
    with_url = [s for s in sources if s.get("url")]
    dated = [s for s in with_url if s.get("access_date")]
    missing_n = len(evidence.get("missing_information") or [])
    ev = []
    missing = []
    score = 0
    if len(with_url) >= 1:
        score += 1
        ev.append("At least one sourced URL is present.")
    else:
        missing.append("Sourced URLs")
    if len(with_url) >= 3:
        score += 1
        ev.append("Three or more sourced URLs are present.")
    else:
        missing.append("Three independent sources")
    if with_url and len(dated) == len(with_url):
        score += 1
        ev.append("Sourced URLs include access dates.")
    else:
        missing.append("Access dates on every source")
    if evidence.get("live"):
        score += 1
        ev.append("Live web research was used.")
    else:
        missing.append("Live web research")
    fabricated_as_facts = bool(evidence.get("fabricated_as_facts"))
    if not fabricated_as_facts:
        score += 1
        ev.append("Unverified metrics were not presented as facts.")
    else:
        score = min(score, 1)
        missing.append("Unverified metrics were treated as facts")
    if missing_n >= 4 and not with_url:
        score = min(score, 2)
        missing.append("Several critical data points remain Not verified")
    if not with_url:
        score = min(score, 1)
    return _component(
        "evidence_confidence",
        score,
        "Confidence rises with dated URLs and live research, and falls when key market stats are missing or unverified.",
        ev,
        missing,
        researched_at,
    )


def recommendation_for(total: int, confidence: int, missing_count: int) -> str:
    if confidence < 2 or (total < 30 and missing_count >= 4):
        return "Insufficient Evidence"
    if total >= 75 and confidence >= 3:
        return "Strong Opportunity"
    if total >= 55:
        return "Promising—Needs Positioning"
    if total >= 40:
        return "Test Before Building"
    return "Weak Opportunity"


def compute_factory_advantage(inputs: dict, evidence: dict | None = None) -> dict:
    """Deterministic 0–100 Factory Advantage Score from inputs + evidence."""
    researched_at = _clean((evidence or {}).get("researched_at")) or utc_today()
    evidence = dict(evidence or {})
    evidence.setdefault("sources", [])
    evidence.setdefault("missing_information", [])
    evidence.setdefault("unverified_metrics", list(UNVERIFIED_METRIC_KEYS))
    evidence.setdefault("live", False)

    demand = score_demand(inputs, evidence, researched_at)
    competition = score_competition(inputs, evidence, researched_at)
    urgency = score_urgency(inputs, evidence, researched_at)
    monetization = score_monetization(inputs, evidence, researched_at)
    differentiation = score_differentiation(inputs, evidence, researched_at)
    production = score_production_fit(inputs, researched_at)
    confidence = score_evidence_confidence(evidence, researched_at)

    components = {
        "demand": demand,
        "competition_opportunity": competition,
        "buyer_urgency": urgency,
        "monetization_potential": monetization,
        "differentiation_potential": differentiation,
        "production_fit": production,
        "evidence_confidence": confidence,
    }
    total = sum(row["score"] for row in components.values())
    missing_all = []
    for row in components.values():
        missing_all.extend(row.get("missing_evidence") or [])
    reco = recommendation_for(total, confidence["score"], len(set(missing_all)))
    return {
        "total": total,
        "max": 100,
        "recommendation": reco,
        "components": components,
        "researched_at": researched_at,
        "disclaimer": DISCLAIMER,
        "formula": (
            "total = demand(0-20) + competition_opportunity(0-20) + buyer_urgency(0-15) "
            "+ monetization_potential(0-15) + differentiation_potential(0-15) "
            "+ production_fit(0-10) + evidence_confidence(0-5)"
        ),
    }


def three_differentiation_opportunities(inputs: dict) -> list[dict]:
    topic = _clean(inputs.get("topic") or inputs.get("niche") or inputs.get("interest")) or "this topic"
    audience = _clean(inputs.get("audience")) or "the stated audience"
    product_type = normalize_product_type(inputs.get("product_type") or "Not Sure Yet")
    problem = _clean(inputs.get("customer_problem")) or "the stated customer problem"
    return [
        {
            "title": f"{product_type} built around {problem}",
            "angle": f"Lead with the problem ({problem}) instead of a generic {topic} catalog.",
            "why_original": "Most listings describe the format; this one sells the outcome.",
        },
        {
            "title": f"Series starter for {audience}",
            "angle": f"Position the first {product_type} as issue one of a named series, not a one-off.",
            "why_original": "A series promise creates a reason to return without copying competing titles.",
        },
        {
            "title": f"Companion format for {topic}",
            "angle": f"Pair the {product_type} with a small adjacent Factory format (worksheet, short guide, or printable pack) that the same buyer already needs.",
            "why_original": "The adjacent format is a product-line move, not a clone of the primary competitor.",
        },
    ]


def related_product_opportunities(inputs: dict, limit: int = 5) -> list[dict]:
    topic = _clean(inputs.get("topic") or inputs.get("niche") or inputs.get("interest")) or "this topic"
    selected = normalize_product_type(inputs.get("product_type") or "Not Sure Yet")
    catalog = [
        ("Coloring Book", "A themed coloring book for the same buyer."),
        ("Crossword Puzzle Book", "A crossword book using the same vocabulary and world."),
        ("Word Search Book", "A word-search pack that reuses the theme with lower production effort."),
        ("Ebook", "A short how-to or story companion ebook for the same audience."),
        ("Math Worksheet", "A practice pack if the audience includes learners."),
        ("Workbook", "A guided workbook if the buyer wants exercises, not just reading."),
    ]
    out = []
    for label, why in catalog:
        if label.lower() == selected.lower():
            continue
        out.append({"product_type": label, "idea": f"{label} on {topic}", "why": why})
        if len(out) >= limit:
            break
    return out


def series_builder(inputs: dict) -> dict:
    topic = _clean(inputs.get("topic") or inputs.get("niche") or inputs.get("interest")) or "this topic"
    product_type = normalize_product_type(inputs.get("product_type") or "Not Sure Yet")
    audience = _clean(inputs.get("audience")) or "the stated audience"
    bookish = product_type.lower() in {
        "ebook",
        "coloring book",
        "word search book",
        "crossword puzzle book",
        "workbook",
        "not sure yet",
    }
    return {
        "applies_to_books": True,
        "applies_to_non_books": True,
        "selected_product_type": product_type,
        "book_line": {
            "name": f"{topic} series",
            "installments": [
                f"Book 1: {topic} starter for {audience}",
                f"Book 2: seasonal or skill-up sequel",
                f"Book 3: advanced / collector edition",
            ],
            "note": "For ebooks and activity books. Titles are planning labels, not live listings.",
        },
        "non_book_line": {
            "name": f"{topic} product line",
            "installments": [
                f"{product_type} core offer",
                "Printable companion pack or worksheet set",
                "Lead magnet / sample that points back to the paid offer",
            ],
            "note": "Works for worksheets, printables, and other non-book Factory types.",
        },
        "is_book_format": bookish,
    }


def pricing_scenarios(inputs: dict) -> dict:
    user_price = _clean(inputs.get("target_price"))
    return {
        "user_stated_price": user_price or NOT_VERIFIED,
        "low": NOT_VERIFIED,
        "mid": NOT_VERIFIED,
        "high": NOT_VERIFIED,
        "note": (
            "Price comps, BSR, and revenue are Not verified. "
            "The user-stated target price is an input, not a market fact."
        ),
        "scenarios": [
            {"label": "Test price", "price": user_price or NOT_VERIFIED, "intent": "Validate willingness to pay without claiming market averages."},
            {"label": "Catalog price", "price": NOT_VERIFIED, "intent": "Set after verified comps exist."},
            {"label": "Bundle / series price", "price": NOT_VERIFIED, "intent": "Only after a second format is real."},
        ],
    }


def build_advantage_report(inputs: dict, *, opportunities: list[dict], recommendation: dict, evidence: dict, score: dict) -> dict:
    topic = _clean(inputs.get("topic") or inputs.get("niche") or inputs.get("interest"))
    product_type = normalize_product_type(inputs.get("product_type") or "")
    diffs = three_differentiation_opportunities(inputs)
    top = opportunities[0] if opportunities else {}
    return {
        "A_opportunity_summary": {
            "title": "Opportunity Summary",
            "topic": topic,
            "audience": _clean(inputs.get("audience")),
            "product_type": product_type,
            "score_total": score["total"],
            "recommendation": score["recommendation"],
            "why": _clean((recommendation or {}).get("why_selected"))
            or _clean(top.get("why_opportunity"))
            or "Review the evidence below before building.",
            "what_to_build": _clean((recommendation or {}).get("best_product"))
            or _clean(top.get("product_idea"))
            or topic,
        },
        "B_demand_signals": {
            "title": "Demand Signals",
            "score": score["components"]["demand"],
            "signals": [s.get("excerpt") for s in (evidence.get("sources") or []) if s.get("excerpt")],
            "search_volume": NOT_VERIFIED,
            "note": "Search volume is Not verified unless a sourced measurement is present.",
        },
        "C_competition": {
            "title": "Competition",
            "score": score["components"]["competition_opportunity"],
            "competitors": evidence.get("competitors") or [],
            "bsr": NOT_VERIFIED,
            "reviews": NOT_VERIFIED,
            "note": "Competitor BSR, review counts, and sales are Not verified when no authorized source is attached.",
        },
        "D_customer_language": {
            "title": "Customer Language",
            "problem": _clean(inputs.get("customer_problem")),
            "phrases": [
                p
                for p in (
                    _clean(inputs.get("customer_problem")),
                    _clean(inputs.get("audience")),
                    _clean(inputs.get("keywords")),
                )
                if p
            ],
            "keywords_input": _clean(inputs.get("keywords")),
        },
        "E_pricing_scenarios": {
            "title": "Pricing scenarios",
            **pricing_scenarios(inputs),
        },
        "F_keywords": {
            "title": "Keywords",
            "user_keywords": [k.strip() for k in _clean(inputs.get("keywords")).split(",") if k.strip()],
            "sourced_terms": evidence.get("search_terms") or [],
            "search_volume": NOT_VERIFIED,
        },
        "G_differentiation_plan": {
            "title": "Differentiation Plan",
            "opportunities": diffs,
        },
        "H_related_product_opportunities": {
            "title": "Related Product Opportunities",
            "items": related_product_opportunities(inputs, limit=5),
        },
        "I_series_builder": {
            "title": "Series / Product-Line Builder",
            **series_builder(inputs),
        },
        "disclaimer": DISCLAIMER,
    }


def build_in_factory_report(
    inputs: dict,
    *,
    opportunities: list[dict],
    recommendation: dict,
    evidence: dict,
    score: dict,
    advantage_report: dict | None = None,
    sales_estimate: dict | None = None,
    decision: dict | None = None,
) -> dict:
    """Assemble the user-facing in-Factory report from existing evidence fields.

    Does not invent prices, rankings, reviews, views, dates, products, or URLs.
    Does not create a second scoring system.
    """
    report = advantage_report or {}
    top = opportunities[0] if opportunities else {}
    sourced = [s for s in (evidence.get("sources") or []) if isinstance(s, dict)]
    listings = [c for c in (evidence.get("competitors") or []) if isinstance(c, dict) and c.get("marketplace")]
    if not listings:
        listings = [
            row
            for row in (listing_from_source(s, evidence.get("researched_at")) for s in sourced)
            if row
        ]
    videos = [
        row
        for row in (youtube_from_source(s, evidence.get("researched_at")) for s in sourced)
        if row
    ]
    diffs = ((report.get("G_differentiation_plan") or {}).get("opportunities")) or three_differentiation_opportunities(inputs)
    sales = sales_estimate or estimate_book_sales()
    panel = decision or {}
    reco = score.get("recommendation") or panel.get("recommendation") or "Insufficient Evidence"
    user_decision = panel.get("user_decision") or map_user_decision(reco)
    problem = _clean(inputs.get("customer_problem") or top.get("customer_problem"))
    why = reject_unsupported_trend_language(
        _clean((recommendation or {}).get("why_selected"))
        or _clean(top.get("why_opportunity"))
        or _clean((report.get("A_opportunity_summary") or {}).get("why"))
    )
    dated_signals = []
    for src in _material_sources(sourced):
        if evidence_type_for(src) != "Market trend" and source_class_for(src) != "Search trend":
            continue
        pub = _clean(src.get("publication_date") or src.get("published_at"))
        dated_signals.append(
            {
                "title": evidence_type_for(src),
                "website": src.get("website") or source_website(src.get("url") or ""),
                "date": pub or NOT_VERIFIED,
                "accessed": src.get("access_date") or NOT_VERIFIED,
                "summary": factory_written_summary(src),
                "kind": (
                    "video"
                    if is_youtube_url(src.get("url") or "")
                    else "marketplace"
                    if marketplace_from_url(src.get("url") or "")
                    else "article"
                ),
            }
        )
    observed_prices = [row["price"] for row in listings if row.get("price") and row["price"] != NOT_VERIFIED]
    user_price = _clean(inputs.get("target_price"))
    opp_price = _clean(top.get("price_range"))
    if observed_prices:
        observed_range = ", ".join(observed_prices[:4])
        price_status = "verified_public_fact"
    else:
        observed_range = NOT_VERIFIED
        price_status = "not_verified"
    verified_price_facts = list(evidence.get("verified_facts") or [])
    estimates = [
        {
            "label": "Estimated demand",
            "value": NOT_VERIFIED,
            "basis": sales.get("reason") or "No authorized BSR-to-sales method is configured.",
            "confidence": "unavailable",
            "verified_sales": False,
        }
    ]
    if user_price:
        estimates.append(
            {
                "label": "User-stated target price",
                "value": user_price,
                "basis": "Entered by the user. Not a verified market comparable.",
                "confidence": "user_input",
                "verified_sales": False,
            }
        )
    if opp_price and opp_price != NOT_VERIFIED and not observed_prices:
        estimates.append(
            {
                "label": "Observed price range (unverified)",
                "value": opp_price,
                "basis": "Research note only. Not taken from a verified public listing price.",
                "confidence": "low",
                "verified_sales": False,
            }
        )
    requests = (
        [f"Stated customer problem: {problem} (not independently verified from reviews)"]
        if problem
        else [INSUFFICIENT_EVIDENCE]
    )
    first_diff = diffs[0] if diffs else {}
    citation_sources = [
        {
            "title": s.get("title") or "Untitled",
            "website": s.get("website") or source_website(s.get("url") or ""),
            "date": s.get("access_date") or NOT_VERIFIED,
            "url": s.get("url") or "",
        }
        for s in sourced
        if s.get("url") or s.get("title")
    ]
    components = []
    for key in COMPONENT_CAPS:
        row = dict((score.get("components") or {}).get(key) or {})
        if row:
            row["display_label"] = row.get("display_label") or COMPONENT_DISPLAY_LABELS.get(key) or row.get("label")
            components.append(row)
    return {
        "opportunity_summary": {
            "title": "Opportunity Summary",
            "product_idea": _clean(top.get("product_idea") or inputs.get("topic") or inputs.get("idea")),
            "target_customer": _clean(top.get("target_audience") or inputs.get("audience")),
            "customer_problem": problem or INSUFFICIENT_EVIDENCE,
            "recommended_product_format": normalize_product_type(
                top.get("product_type") or inputs.get("product_type") or ""
            ),
            "why_timely": why or INSUFFICIENT_EVIDENCE,
        },
        "trend_evidence": {
            "title": "Trend Evidence",
            "direction": INSUFFICIENT_EVIDENCE,
            "dated_evidence": dated_signals,
            "signals": dated_signals,
            "note": (
                "Factory does not label an idea trending from general articles. "
                "Direction stays Insufficient evidence until a verified trend measurement exists."
            ),
        },
        "marketplace_competition": {
            "title": "Marketplace Competition",
            "listings": listings,
            "note": (
                "Relevant public listings only. Price, rating, review count, and Amazon BSR "
                "stay Not verified unless an authorized public value was attached."
                if listings
                else (
                    "No verified marketplace listings were collected. "
                    "Amazon, Etsy, Gumroad, and TPT prices, ratings, reviews, and BSR are Not verified."
                )
            ),
        },
        "video_social_evidence": {
            "title": "Video and Social Evidence",
            "videos": videos,
            "interest_summary": (
                "Public YouTube titles/excerpts mention this topic. Views are not sales."
                if videos
                else INSUFFICIENT_EVIDENCE
            ),
            "note": "Do not treat video views as unit sales or revenue.",
        },
        "customer_evidence": {
            "title": "Customer Evidence",
            "recurring_requests": requests,
            "complaints": [INSUFFICIENT_EVIDENCE],
            "missing_features": [INSUFFICIENT_EVIDENCE],
            "underserved_niche": _clean(first_diff.get("angle")) or INSUFFICIENT_EVIDENCE,
            "source_links": [
                {"title": s.get("website") or "Public source", "website": s.get("website")}
                for s in citation_sources
                if s.get("website")
            ],
            "note": "Review-level complaint mining is Not verified. User-stated problems are labeled as such.",
        },
        "price_revenue_signals": {
            "title": "Price and Revenue Signals",
            "observed_price_range": observed_range,
            "common_pricing_position": NOT_VERIFIED if not observed_prices else "Public listing prices shown above",
            "bundle_opportunities": [
                _clean(x.get("idea") or x.get("title"))
                for x in ((report.get("H_related_product_opportunities") or {}).get("items") or [])[:3]
                if _clean(x.get("idea") or x.get("title"))
            ] or [INSUFFICIENT_EVIDENCE],
            "verified_facts": verified_price_facts,
            "estimates": estimates,
            "price_status": price_status,
            "sales_estimate_label": "Estimated demand",
            "sales_estimate_basis": sales.get("reason") or "",
            "sales_estimate_confidence": "unavailable" if not sales.get("available") else "low",
            "verified_sales": False,
            "note": (
                "Verified public facts are separated from estimates. "
                "Factory never labels estimated Amazon sales as verified sales."
            ),
        },
        "competition_opportunity_gap": {
            "title": "Competition and Opportunity Gap",
            "existing_do_well": INSUFFICIENT_EVIDENCE if not listings else "Public listings exist for this format or adjacent offer.",
            "existing_do_poorly": INSUFFICIENT_EVIDENCE,
            "how_to_improve": _clean(first_diff.get("angle")) or INSUFFICIENT_EVIDENCE,
            "proposed_differentiator": _clean(first_diff.get("title") or first_diff.get("why_original")) or INSUFFICIENT_EVIDENCE,
            "opportunities": diffs,
        },
        "factory_advantage_score": {
            "title": "Factory Advantage Score",
            "total": score.get("total"),
            "max": score.get("max") or 100,
            "recommendation": reco,
            "components": components,
            "formula": score.get("formula") or "",
            "disclaimer": DISCLAIMER,
        },
        "decision": {
            "title": "Decision",
            "user_decision": user_decision,
            "internal_recommendation": reco,
            "reasons": panel.get("user_decision_reasons")
            or [
                f"Factory recommendation band: {reco}.",
                panel.get("next_action") or "Review the evidence before building.",
            ],
            "next_action": panel.get("next_action") or "",
        },
        "sources": citation_sources,
        "evidence_used": build_evidence_used(sourced, score=score, evidence=evidence),
        "how_we_know": build_how_we_know(sourced, score=score),
        "disclaimer": DISCLAIMER,
    }


def decision_panel(inputs: dict, score: dict, opportunities: list[dict], evidence: dict) -> dict:
    top = opportunities[0] if opportunities else {}
    missing = []
    for row in (score.get("components") or {}).values():
        missing.extend(row.get("missing_evidence") or [])
    missing.extend(evidence.get("missing_information") or [])
    # unique, stable order
    seen = []
    for item in missing:
        if item not in seen:
            seen.append(item)
    reco = score.get("recommendation") or "Insufficient Evidence"
    user_decision = map_user_decision(reco)
    if reco == "Insufficient Evidence":
        next_action = "Gather live sources before building."
        reasons = [
            "Insufficient evidence. Factory will not treat general articles as validation.",
            "Live marketplace, video, or dated demand signals were not verified.",
        ]
    elif reco == "Strong Opportunity":
        next_action = "Choose Your Advantage, then Build This Product in the matching Factory builder."
        reasons = [
            "The documented Factory Advantage Score and evidence support building a draft.",
            "Open the matching builder as a draft. Factory will not auto-generate a product.",
        ]
    elif reco == "Promising—Needs Positioning":
        next_action = "Tighten the differentiation angle, then build a draft — do not skip the builder review."
        reasons = [
            "There is enough signal to continue, but the offer still needs a clearer angle.",
            "Improve the idea before a full build.",
        ]
    elif reco == "Test Before Building":
        next_action = "Validate demand with a small listing test or more sources before a full build."
        reasons = [
            "Evidence is mixed. Improve the idea or gather more public signals first.",
            "Do not treat this as a validated product yet.",
        ]
    else:
        next_action = "Do not build yet. Revisit the idea or gather better evidence."
        reasons = [
            "The current evidence does not support building this product now.",
            "Avoid spending production time until a stronger gap is documented.",
        ]
    if seen:
        reasons.append("Missing: " + "; ".join(seen[:4]))
    return {
        "demand": score["components"]["demand"]["explanation"],
        "competition": score["components"]["competition_opportunity"]["explanation"],
        "differentiation": score["components"]["differentiation_potential"]["explanation"],
        "price_range": _clean(inputs.get("target_price")) or NOT_VERIFIED,
        "what_to_build": _clean(top.get("product_idea")) or _clean(inputs.get("topic")),
        "product_type": normalize_product_type(
            top.get("product_type") or inputs.get("product_type") or ""
        ),
        "missing_evidence": seen[:12],
        "next_action": next_action,
        "recommendation": reco,
        "user_decision": user_decision,
        "user_decision_reasons": reasons,
        "internal_recommendation": reco,
    }


def collect_inputs(body: dict) -> dict:
    body = body if isinstance(body, dict) else {}
    depth = _clean(body.get("depth")) or DEPTH_FULL
    if depth not in DEPTH_OPTIONS:
        depth = DEPTH_FULL
    product_type = normalize_product_type(
        body.get("product_type") or body.get("preferred_product_type") or ""
    )
    topic = _clean(
        body.get("topic")
        or body.get("idea")
        or body.get("niche")
        or body.get("keyword")
        or body.get("interest")
    )
    return {
        "topic": topic,
        "idea": _clean(body.get("idea") or topic),
        "audience": _clean(body.get("audience")),
        "customer_problem": _clean(body.get("customer_problem") or body.get("problem")),
        "product_type": product_type,
        "sales_platform": _clean(body.get("sales_platform") or body.get("platform")) or "Not sure",
        "expertise": _clean(body.get("expertise") or body.get("experience")),
        "target_price": _clean(body.get("target_price") or body.get("price")),
        "keywords": _clean(body.get("keywords")),
        "depth": depth,
        "niche": _clean(body.get("niche")),
        "interest": _clean(body.get("interest") or topic),
        "difficulty": _clean(body.get("difficulty")),
        "goal": _clean(body.get("goal")),
        "keyword": _clean(body.get("keyword") or topic),
    }


def recommended_mvp_text(
    *,
    product_type: str,
    idea: str,
    audience: str,
    problem: str,
    differentiator: str = "",
) -> str:
    """Plain-language MVP from the existing recommended type/idea — not a new product."""
    pt = normalize_product_type(product_type or "")
    idea_txt = _clean(idea) or "this idea"
    audience_txt = _clean(audience) or "the stated audience"
    problem_txt = _clean(problem) or "the stated customer problem"
    template = MVP_STARTERS.get(pt) or (
        "Start with: a {product_type} for {audience} based on {idea}."
    )
    text = template.format(
        product_type=pt,
        idea=idea_txt,
        audience=audience_txt,
        problem=problem_txt,
    )
    angle = _clean(differentiator)
    if angle and angle.lower() not in (INSUFFICIENT_EVIDENCE.lower(), "insufficient evidence"):
        text = f"{text} Keep the angle specific: {angle.rstrip('.')}."
    return text


def why_we_recommend_text(
    *,
    inputs: dict,
    score: dict,
    opportunities: list[dict],
    evidence: dict,
    recommendation: dict | None = None,
    decision: dict | None = None,
) -> str:
    """2–3 adviser sentences from existing evidence. Never invents sales facts."""
    top = opportunities[0] if opportunities else {}
    reco = recommendation or {}
    panel = decision or {}
    audience = _clean(top.get("target_audience") or inputs.get("audience")) or "this audience"
    problem = _clean(top.get("customer_problem") or inputs.get("customer_problem"))
    product_type = normalize_product_type(
        top.get("product_type") or inputs.get("product_type") or reco.get("best_product_type") or ""
    )
    comps = score.get("components") or {}
    demand_signal = plain_component_signal(comps.get("demand"))
    standout_signal = plain_component_signal(comps.get("differentiation_potential"))
    sourced = [s for s in (evidence.get("sources") or []) if isinstance(s, dict)]
    live = bool(evidence.get("live"))
    missing = [m for m in (panel.get("missing_evidence") or []) if _clean(str(m))]
    sentences = []
    if demand_signal == "Good Signal":
        if live and sourced:
            sentences.append(
                f"Public market signals support demand for a {product_type} aimed at {audience}."
            )
        else:
            sentences.append(
                f"This {product_type} is aimed at {audience}, and Factory found supporting demand context."
            )
    elif demand_signal == "More Research Needed":
        sentences.append(f"Demand for this {product_type} is not fully verified yet.")
    else:
        sentences.append(f"Demand signals for this {product_type} are mixed or limited.")
    if problem:
        sentences.append(f"The customer problem is clear: {problem.rstrip('.')}.")
    else:
        sentences.append(
            "The customer problem still needs a sharper statement before this is a strong offer."
        )
    why = reject_unsupported_trend_language(
        _clean(reco.get("why_selected")) or _clean(top.get("why_opportunity"))
    )
    if standout_signal == "Good Signal":
        if why:
            sentences.append(why if why.endswith(".") else why + ".")
        else:
            sentences.append(
                "There is room to stand out if you keep a specific angle instead of a generic catalog."
            )
    elif missing:
        sentences.append(
            "Some sales, ranking, and review numbers stay Not verified, so this is not a guaranteed result."
        )
    else:
        sentences.append(
            "Ability to stand out is uncertain until a clearer differentiator is documented."
        )
    return " ".join(sentences[:3])


def build_recommendation_summary(
    inputs: dict,
    *,
    score: dict,
    opportunities: list[dict],
    evidence: dict,
    recommendation: dict | None = None,
    decision: dict | None = None,
) -> dict:
    """Customer Recommendation Summary. Maps existing scores; does not rescore."""
    top = opportunities[0] if opportunities else {}
    reco = recommendation or {}
    panel = decision or {}
    internal = (
        score.get("recommendation")
        or panel.get("internal_recommendation")
        or panel.get("recommendation")
        or "Insufficient Evidence"
    )
    user_decision = panel.get("user_decision") or map_user_decision(internal)
    product_name = (
        _clean(reco.get("best_product"))
        or _clean(top.get("product_idea"))
        or _clean(inputs.get("topic") or inputs.get("idea"))
        or "This idea"
    )
    product_type = normalize_product_type(
        reco.get("best_product_type")
        or top.get("product_type")
        or inputs.get("product_type")
        or ""
    )
    audience = _clean(top.get("target_audience") or inputs.get("audience"))
    problem = _clean(top.get("customer_problem") or inputs.get("customer_problem"))
    diffs = three_differentiation_opportunities(inputs)
    first_diff = diffs[0] if diffs else {}
    differentiator = _clean(first_diff.get("angle"))
    comps = score.get("components") or {}
    signals = []
    for key, label in CUSTOMER_COMPONENT_SIGNALS:
        row = comps.get(key) if isinstance(comps, dict) else None
        signals.append({"key": key, "label": label, "signal": plain_component_signal(row)})
    return {
        "product_name": product_name,
        "product_type": product_type,
        "opportunity_label": plain_opportunity_label(internal, user_decision),
        "internal_recommendation": internal,
        "user_decision": user_decision,
        "why_we_recommend": why_we_recommend_text(
            inputs=inputs,
            score=score,
            opportunities=opportunities,
            evidence=evidence,
            recommendation=reco,
            decision=panel,
        ),
        "what_to_build": recommended_mvp_text(
            product_type=product_type,
            idea=product_name,
            audience=audience,
            problem=problem,
            differentiator=differentiator,
        ),
        "component_signals": signals,
        "how_determined": HOW_DETERMINED_PLAIN,
        "disclaimer": DISCLAIMER,
        "missing_evidence": list(panel.get("missing_evidence") or [])[:8],
    }


def attach_advantage(
    payload: dict,
    *,
    inputs: dict,
    sources: list[dict] | None = None,
    live: bool = False,
    ai_notes: list[str] | None = None,
    competition_level: str | None = None,
    competition_verified: bool = False,
    competitors: list[dict] | None = None,
    search_terms: list[str] | None = None,
    provider_error: str | None = None,
) -> dict:
    """Add Factory Market Advantage fields onto an existing research payload."""
    researched_at = utc_today()
    sourced = [normalize_source(s, researched_at) for s in (sources or payload.get("sources") or [])]
    opportunities = coerce_selected_product_type(
        list(payload.get("opportunities") or []),
        inputs.get("product_type") or "",
    )
    reco = dict(payload.get("recommendation") or {})
    selected_type = normalize_product_type(inputs.get("product_type") or "")
    if selected_type and selected_type != "Not Sure Yet":
        reco["best_product_type"] = selected_type
        reco["best_format"] = selected_type
        payload["product_type"] = selected_type

    diffs = three_differentiation_opportunities(inputs)
    evidence = classify_evidence(
        sources=sourced,
        inputs=inputs,
        live=live,
        ai_notes=ai_notes,
        unverified_metrics=list(UNVERIFIED_METRIC_KEYS),
    )
    evidence["competition_level"] = _clean(competition_level) or _clean(
        (opportunities[0] if opportunities else {}).get("competition")
    )
    evidence["competition_verified"] = bool(competition_verified and live)
    evidence["differentiation_count"] = len(diffs)
    listing_rows = []
    seen_listing_urls = set()
    for raw in list(competitors or []) + sourced:
        if not isinstance(raw, dict):
            continue
        row = listing_from_source(raw, researched_at)
        if not row:
            continue
        key = row.get("listing_url") or row.get("url") or row.get("title")
        if key in seen_listing_urls:
            continue
        seen_listing_urls.add(key)
        listing_rows.append(row)
    evidence["competitors"] = listing_rows
    evidence["youtube_videos"] = [
        row
        for row in (youtube_from_source(s, researched_at) for s in sourced)
        if row
    ]
    evidence["search_terms"] = [str(t) for t in (search_terms or []) if str(t).strip()]
    evidence["researched_at"] = researched_at
    evidence["fabricated_as_facts"] = False

    score = compute_factory_advantage(inputs, evidence)
    report = build_advantage_report(
        inputs,
        opportunities=opportunities,
        recommendation=reco,
        evidence=evidence,
        score=score,
    )
    # Backward-compatible legacy report keys used by saved research reopen.
    legacy_report = dict(payload.get("report") or {})
    legacy_report.setdefault("opportunity_score", score["total"])
    legacy_report.setdefault("niche_summary", report["A_opportunity_summary"]["why"])
    legacy_report.setdefault("target_audience", inputs.get("audience"))
    legacy_report.setdefault("customer_problems", [inputs["customer_problem"]] if inputs.get("customer_problem") else [])
    legacy_report.setdefault("search_terms", evidence.get("search_terms") or [])
    legacy_report.setdefault("product_ideas", [o.get("product_idea") for o in opportunities if o.get("product_idea")])
    legacy_report.setdefault("best_format", selected_type or reco.get("best_product_type") or "")
    legacy_report.setdefault("price_range", inputs.get("target_price") or NOT_VERIFIED)
    legacy_report.setdefault("competition", evidence.get("competition_level") or NOT_VERIFIED)
    legacy_report.setdefault("why_worth_creating", report["A_opportunity_summary"]["why"])
    legacy_report.setdefault("next_step", reco.get("next_step") or "Choose Your Advantage")

    payload = dict(payload)
    payload["opportunities"] = opportunities
    payload["recommendation"] = reco
    payload["sources"] = sourced
    payload["inputs"] = inputs
    payload["product_type"] = selected_type or payload.get("product_type") or "Not Sure Yet"
    payload["factory_advantage"] = score
    payload["advantage_report"] = report
    payload["evidence"] = evidence
    payload["decision_panel"] = decision_panel(inputs, score, opportunities, evidence)
    payload["disclaimer"] = DISCLAIMER
    payload["sales_estimate"] = estimate_book_sales()
    payload["in_factory_report"] = build_in_factory_report(
        inputs,
        opportunities=opportunities,
        recommendation=reco,
        evidence=evidence,
        score=score,
        advantage_report=report,
        sales_estimate=payload["sales_estimate"],
        decision=payload["decision_panel"],
    )
    payload["recommendation_summary"] = build_recommendation_summary(
        inputs,
        score=score,
        opportunities=opportunities,
        evidence=evidence,
        recommendation=reco,
        decision=payload["decision_panel"],
    )
    payload["internal_evidence_record"] = build_internal_evidence_record(
        sourced,
        research_result=reco.get("why_selected") or score.get("recommendation") or "",
    )
    payload["workflow"] = "factory_market_advantage"
    payload["workflow_label"] = WORKFLOW_LABEL
    payload["tagline"] = WORKFLOW_TAGLINE
    payload["report"] = legacy_report
    payload["researched_at"] = researched_at
    if provider_error:
        payload["provider_error"] = provider_error
        payload["retryable"] = True
    # Keep opportunity_score as the transparent total for old UI cards.
    for opp in payload["opportunities"]:
        if isinstance(opp, dict) and not opp.get("factory_advantage"):
            opp["opportunity_score"] = score["total"]
            opp["factory_advantage_total"] = score["total"]
    return payload


def draft_handoff_payload(
    *,
    opportunity: dict,
    research: dict,
    inputs: dict | None = None,
) -> dict:
    """Create a DRAFT product_plan payload. Never marks APPROVED/LOCKED. Never generates a product."""
    op = dict(opportunity or {})
    research = dict(research or {})
    inputs = dict(inputs or research.get("inputs") or {})
    product_type = normalize_product_type(
        op.get("product_type") or inputs.get("product_type") or research.get("product_type") or ""
    )
    builder = resolve_factory_builder(product_type)
    title = _clean(op.get("product_idea") or inputs.get("topic") or "Untitled product")
    plan = {
        "product_title": title,
        "subtitle": "",
        "product_type": product_type,
        "target_audience": _clean(op.get("target_audience") or inputs.get("audience")),
        "customer_problem": _clean(op.get("customer_problem") or inputs.get("customer_problem")),
        "product_promise": _clean(op.get("why_opportunity")),
        "main_transformation": "",
        "price_range": _clean(op.get("price_range") or inputs.get("target_price")) or NOT_VERIFIED,
        "product_description": _clean(op.get("why_opportunity")),
        "outline": [],
        "bonus_ideas": [],
        "cover_concept": "",
        "sales_angle": _clean(op.get("sales_angle")),
        "marketing_hook": "",
        "next_step": "Review in the product builder. Do not auto-generate.",
    }
    return {
        "artifact_state": ArtifactState.DRAFT.value,
        "stage": "product_plan_saved",
        "generated": False,
        "auto_generated": False,
        "product_type": product_type,
        "niche": _clean(op.get("niche") or inputs.get("topic") or research.get("niche")),
        "audience": plan["target_audience"],
        "mode": research.get("mode") or "ai_estimated",
        "inputs": inputs,
        "opportunity": op,
        "opportunities": research.get("opportunities") or [op],
        "recommendation": research.get("recommendation") or {},
        "factory_advantage": research.get("factory_advantage"),
        "advantage_report": research.get("advantage_report"),
        "in_factory_report": research.get("in_factory_report"),
        "internal_evidence_record": research.get("internal_evidence_record") or [],
        "evidence": research.get("evidence"),
        "decision_panel": research.get("decision_panel"),
        "disclaimer": DISCLAIMER,
        "sales_estimate": research.get("sales_estimate") or estimate_book_sales(),
        "report": research.get("report") or {},
        "sources": research.get("sources") or [],
        "plan": plan,
        "builder": builder,
        "workflow": "factory_market_advantage",
    }


def builder_prefill_from_plan(plan: dict) -> dict:
    title = (plan or {}).get("product_title") or ""
    audience = (plan or {}).get("target_audience") or ""
    return {
        "topic": title,
        "theme": title,
        "title": title,
        "worksheet_title": title,
        "book_title": title,
        "subtitle": (plan or {}).get("subtitle") or "",
        "audience": audience,
        "age_group": audience,
        "product_type": (plan or {}).get("product_type") or "",
        "cta": (plan or {}).get("marketing_hook") or "",
        "image_concept": (plan or {}).get("cover_concept") or "",
        "customer_problem": (plan or {}).get("customer_problem") or "",
        "product_promise": (plan or {}).get("product_promise") or "",
        "main_transformation": (plan or {}).get("main_transformation") or "",
    }
