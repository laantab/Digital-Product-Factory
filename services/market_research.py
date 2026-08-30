"""Market Research module.

Produces a structured "opportunity report" for a niche/audience/product-type.
Uses live Tavily web search when TAVILY_API_KEY is set; otherwise falls back to
an AI-estimated report that is clearly labelled as such.

Factory Market Advantage attaches a transparent 0–100 score and report sections
A–I onto this existing payload. Old keys stay in place for saved research.
"""
import logging
import os
import re
from datetime import datetime, timezone

from ai_client import chat_json
from services.factory_advantage import (
    DEPTH_QUICK,
    attach_advantage,
    classify_evidence,
    collect_inputs,
    compact_evidence_summary,
    compute_factory_advantage,
    normalize_product_type,
    normalize_source,
    reject_unsupported_trend_language,
    utc_today,
)

logger = logging.getLogger(__name__)

# Customer-facing degraded-mode notices.
#
# These strings reach the browser via `provider_error`, so they must never carry
# exception text: a raw provider error leaks API keys (an OpenAI 401 echoes a
# masked-but-identifiable key), model names, and stack detail into the customer's
# page. The full exception is still logged server-side with exc_info=True, which
# is where it belongs -- the operator needs it, the customer does not.
AI_UNAVAILABLE_MESSAGE = (
    "Our research assistant is temporarily unavailable, so this report was built "
    "from your inputs alone. Try again in a moment for a fully researched report."
)
LIVE_RESEARCH_UNAVAILABLE_MESSAGE = (
    "Live web research is temporarily unavailable, so this report relies on fewer "
    "outside sources than usual."
)
LIVE_RESEARCH_NOT_CONFIGURED_MESSAGE = (
    "Live web research is unavailable (no Tavily key configured)."
)

PRODUCT_TYPES = [
    "Ebook",
    "Workbook",
    "Checklist",
    "Coloring Book",
    "Word Search Book",
    "Crossword Puzzle Book",
    "Flip Book",
    "Math Worksheet",
    "Not Sure Yet",
]

_REPORT_KEYS = [
    "niche_summary",
    "target_audience",
    "customer_problems",
    "search_terms",
    "product_ideas",
    "best_format",
    "title_ideas",
    "price_range",
    "difficulty",
    "competition",
    "opportunity_score",
    "why_worth_creating",
    "next_step",
]


def _test_mode() -> bool:
    return str(os.environ.get("FACTORY_TEST_MODE") or "") == "1"


def _tavily_context(
    niche: str,
    audience: str,
    *,
    depth: str = "",
) -> tuple[bool, str, list[dict], str | None]:
    """Return (live_used, context_text, sources, provider_error).

    Fails open: if Tavily is missing OR errors out, returns live_used=False so the
    caller can still assemble a report. The UI keeps the user's inputs and may retry.
    FACTORY_TEST_MODE never performs a live Tavily call.
    """
    if _test_mode():
        return False, "", [], None
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return False, "", [], LIVE_RESEARCH_NOT_CONFIGURED_MESSAGE
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=key)
        query = (
            f"demand, audience and competition for {niche} digital products"
            + (f" for {audience}" if audience else "")
        )
        advanced = depth != DEPTH_QUICK
        search = client.search(
            query=query,
            search_depth="advanced" if advanced else "basic",
            max_results=8 if advanced else 4,
            include_answer=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Tavily search failed; falling back to AI-estimated research: %s", exc, exc_info=True)
        return False, "", [], LIVE_RESEARCH_UNAVAILABLE_MESSAGE

    access_date = datetime.now(timezone.utc).date().isoformat()
    sources = [
        {
            "title": r.get("title", "Untitled"),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
            "excerpt": r.get("content", ""),
            "access_date": access_date,
            "confidence": "medium",
        }
        for r in search.get("results", [])
    ]
    answer = search.get("answer", "")
    context = ""
    if answer:
        context += f"Web summary: {answer}\n\n"
    context += "\n\n".join(
        f"Source: {s['title']} ({s['url']})\n{s['content']}" for s in sources
    )
    # Tavily was reachable and returned a response — this is a live result even if
    # the body is thin.
    return True, context, sources, None


_OPP_KEYS = [
    "niche",
    "product_idea",
    "product_type",
    "target_audience",
    "customer_problem",
    "why_opportunity",
    "price_range",
    "difficulty",
    "competition",
    "opportunity_score",
    "sales_angle",
]

_RECO_KEYS = [
    "best_niche",
    "best_product",
    "best_product_type",
    "why_selected",
    "best_format",
    "suggested_title",
    "next_step",
]

DISCOVERY_FAILURE_MESSAGE = (
    "We couldn't complete the market research. Your idea and filters have been "
    "preserved. Please try again."
)
DISCOVERY_RESULTS_TITLE = "Top 10 Digital Product Opportunities Right Now"
DISCOVERY_DISCLAIMER = (
    "Market scores, pricing observations, and demand indicators are research "
    "estimates based on available public evidence. They do not guarantee sales "
    "or earnings."
)
DISCOVERY_MAX = 10
DISCOVERY_AUDIENCES = (
    "Parents",
    "Teachers",
    "Small-business owners",
    "Seniors",
    "Photographers",
    "Fitness beginners",
    "General / Any audience",
)
DISCOVERY_PLATFORMS = (
    "Amazon",
    "Etsy",
    "Gumroad",
    "Lemon Squeezy",
    "Shopify",
    "Not sure / Any",
)
_ANY_AUDIENCE = {"", "general / any audience", "general", "any audience", "any"}
_ANY_TYPE = {"", "not sure yet", "any product type", "any"}
_ANY_PLATFORM = {"", "not sure", "not sure / any", "any"}
_BESTSELLER_RE = re.compile(r"\b(?:verified\s+)?best[\s-]?sell(?:er|ing)?s?\b", re.I)


def _clamp_score(value) -> int:
    try:
        score = int(round(float(value or 0)))
    except (TypeError, ValueError):
        score = 0
    return max(1, min(100, score)) if score else 0


def _coerce_opportunities(raw: dict) -> tuple[list[dict], dict]:
    items = raw.get("opportunities")
    if not isinstance(items, list):
        items = []
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        opp = {key: item.get(key, "") for key in _OPP_KEYS}
        opp["opportunity_score"] = _clamp_score(opp.get("opportunity_score"))
        cleaned.append(opp)
    # Rank by score (desc); fall back to original order for ties.
    cleaned.sort(key=lambda o: o["opportunity_score"], reverse=True)
    for idx, opp in enumerate(cleaned, start=1):
        opp["rank"] = idx

    reco_raw = raw.get("recommendation")
    if not isinstance(reco_raw, dict):
        reco_raw = {}
    recommendation = {key: reco_raw.get(key, "") for key in _RECO_KEYS}
    # Default the recommendation to the top-ranked opportunity if the model
    # left it blank.
    if cleaned:
        top = cleaned[0]
        recommendation["best_product"] = recommendation["best_product"] or top["product_idea"]
        recommendation["best_product_type"] = (
            recommendation["best_product_type"] or top["product_type"]
        )
        recommendation["best_format"] = recommendation["best_format"] or top["product_type"]
        recommendation["best_niche"] = recommendation["best_niche"] or top.get("niche", "")
    return cleaned, recommendation


def _idea_name(topic: str, product_type: str) -> str:
    """"budget planner for young families" + "Budget Planner" -> no stutter.

    The topic a customer types very often already names the product type
    ("budget planner for young families"), and blindly appending it produced
    "budget planner for young families Budget Planner" on the results page.
    """
    topic = (topic or "").strip()
    ptype = (product_type or "").strip()
    if not ptype:
        return topic
    if not topic:
        return ptype
    if ptype.lower() in topic.lower():
        return topic
    return f"{topic} {ptype}"


def _as_need_phrase(problem: str) -> str:
    """Turn a stated problem into something that reads after "addressing ...".

    Customers state the problem as a full clause ("families overspend because
    they have no simple monthly system"), which is ungrammatical after a
    preposition. Wrapping it keeps the customer's own words without producing
    "addressing families overspend because ...".
    """
    problem = (problem or "").strip().rstrip(".")
    if not problem:
        return "the stated need"
    return f"this problem: {problem}"


def _offline_raw(inputs: dict) -> dict:
    """Deterministic opportunities from user inputs when AI is blocked or unavailable."""
    topic = (inputs.get("topic") or inputs.get("niche") or inputs.get("interest") or "Untitled idea").strip()
    audience = (inputs.get("audience") or "").strip()
    problem = (inputs.get("customer_problem") or "").strip()
    selected = normalize_product_type(inputs.get("product_type") or "")
    if selected and selected != "Not Sure Yet":
        types = [selected] * 5
    else:
        types = [
            "Ebook",
            "Coloring Book",
            "Crossword Puzzle Book",
            "Word Search Book",
            "Math Worksheet",
        ]
    opportunities = []
    for idx, ptype in enumerate(types, start=1):
        opportunities.append(
            {
                "niche": inputs.get("niche") or topic,
                "product_idea": _idea_name(topic, ptype),
                "product_type": ptype,
                "target_audience": audience,
                "customer_problem": problem,
                "why_opportunity": (
                    f"A {ptype} for {audience or 'this audience'} addressing "
                    f"{_as_need_phrase(problem)}."
                ),
                "price_range": inputs.get("target_price") or "",
                "difficulty": inputs.get("difficulty") or "Medium",
                "competition": "",
                "opportunity_score": 0,
                "sales_angle": problem or topic,
            }
        )
    top = opportunities[0]
    recommendation = {
        "best_niche": top["niche"],
        "best_product": top["product_idea"],
        "best_product_type": top["product_type"],
        "why_selected": top["why_opportunity"],
        "best_format": top["product_type"],
        "suggested_title": top["product_idea"],
        "next_step": "Choose Your Advantage",
    }
    return {"opportunities": opportunities, "recommendation": recommendation}


def _safe_chat_json(system: str, user: str, inputs: dict, max_completion_tokens: int = 3500) -> tuple[dict, str | None]:
    if _test_mode():
        return _offline_raw(inputs), None
    try:
        raw = chat_json(system=system, user=user, max_completion_tokens=max_completion_tokens)
        if not isinstance(raw, dict):
            raw = {}
        return raw, None
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Research AI call failed; using input-backed draft: %s", exc, exc_info=True)
        return _offline_raw(inputs), AI_UNAVAILABLE_MESSAGE


def discover_products(
    interest: str,
    audience: str,
    product_type: str,
    difficulty: str,
    goal: str,
    niche: str = "",
    **kwargs,
) -> dict:
    """Ranked product opportunities + a single best recommendation.

    Powers both Market Research paths:
    - Path 1 ("I already have a niche"): ``niche`` is set, so every opportunity
      must stay INSIDE that niche.
    - Path 2 ("Find the best niche for me"): ``niche`` is empty and the analysis
      explores broadly from an optional ``interest`` area.
    Everything else is an optional preference.

    Extra kwargs (topic, customer_problem, sales_platform, expertise, target_price,
    keywords, depth) feed Factory Market Advantage without changing old callers.
    """
    body = {
        "interest": interest,
        "audience": audience,
        "product_type": product_type,
        "difficulty": difficulty,
        "goal": goal,
        "niche": niche,
        **kwargs,
    }
    if not body.get("topic") and (niche or interest):
        body["topic"] = (niche or interest)
    inputs = collect_inputs(body)
    interest = inputs["interest"]
    audience = inputs["audience"]
    product_type = inputs["product_type"]
    difficulty = inputs["difficulty"]
    goal = inputs["goal"]
    niche = inputs["niche"]

    # Prefer the explicit niche for live research; otherwise use the broad interest.
    search_subject = niche or interest or inputs["topic"]
    live_used, context, sources, provider_error = (False, "", [], None)
    if search_subject:
        live_used, context, sources, provider_error = _tavily_context(
            search_subject, audience, depth=inputs.get("depth") or ""
        )
    sources = _merge_sources(sources, kwargs.get("carried_sources"))
    mode = "live" if live_used else "ai_estimated"

    if context:
        source_clause = (
            "Base your analysis on the live web research provided below.\n\n"
            f"LIVE WEB RESEARCH:\n{context[:14000]}"
        )
    else:
        source_clause = (
            "No live web data is available, so produce your best expert estimate "
            "based on general market knowledge. Do not invent search volume, BSR, "
            "revenue, review counts, or prices. Use 'Not verified' for those."
        )

    prefs = []
    if niche:
        prefs.append(
            f'The user already has a niche: "{niche}". EVERY opportunity MUST be a '
            "distinct digital product INSIDE this niche. Do not drift to other "
            "niches. Set each opportunity's \"niche\" field to this niche (or a "
            "specific sub-niche within it)."
        )
    else:
        prefs.append(
            f"Broad interest area: {interest}" if interest
            else "The user has no specific niche, so explore broadly across "
            "popular, beginner-friendly digital products and identify the best "
            "niche to enter."
        )
    if audience:
        prefs.append(f"Preferred target audience: {audience}")
    if product_type and product_type != "Not Sure Yet":
        prefs.append(
            f'Preferred product type: {product_type}. EVERY opportunity MUST use '
            f'this exact product_type string. Do not convert it to Ebook.'
        )
    if difficulty:
        prefs.append(f"Preferred difficulty level: {difficulty}")
    if goal:
        prefs.append(f"User's goal: {goal}")
    if inputs.get("customer_problem"):
        prefs.append(f"Customer problem: {inputs['customer_problem']}")
    if inputs.get("sales_platform"):
        prefs.append(f"Sales platform: {inputs['sales_platform']}")
    if inputs.get("expertise"):
        prefs.append(f"Creator experience: {inputs['expertise']}")
    if inputs.get("target_price"):
        prefs.append(f"User-stated target price: {inputs['target_price']}")
    if inputs.get("keywords"):
        prefs.append(f"Keywords: {inputs['keywords']}")
    prefs.append(f"Research depth: {inputs.get('depth')}")
    prefs_block = "\n".join(f"- {p}" for p in prefs)

    raw, ai_error = _safe_chat_json(
        system=(
            "You are a digital-product market research analyst who helps "
            "beginners decide what to build. You compare several options and "
            "commit to a single clear recommendation. You are concrete, "
            "realistic, and encouraging. Never invent search volume, BSR, "
            "sales, revenue, or review counts."
        ),
        user=(
            "Generate a ranked list of digital-product opportunities, then pick "
            "the single best one to build.\n\n"
            f"PREFERENCES:\n{prefs_block}\n\n"
            f"{source_clause}\n\n"
            "Return a JSON object with EXACTLY these keys:\n"
            '- "opportunities": array of 5 objects, each with keys: '
            '"niche" (string, the specific niche this product serves), '
            '"product_idea" (string), "product_type" (string), '
            '"target_audience" (string), "customer_problem" (string), '
            '"why_opportunity" (string, 1-2 sentences), "price_range" (string, '
            'e.g. "$9 - $19" or "Not verified"), "difficulty" (one of "Easy", "Medium", "Hard"), '
            '"competition" (one of "Low", "Medium", "High"), '
            '"opportunity_score" (integer 1-100), "sales_angle" (string).\n'
            '- "recommendation": object with keys "best_niche" (string), '
            '"best_product" (string), "best_product_type" (string), '
            '"why_selected" (string, 2-3 sentences), "best_format" (string), '
            '"suggested_title" (string), "next_step" (string, one clear action).\n'
            "Make the opportunities genuinely different from each other. The "
            "recommendation must match the strongest opportunity. Do not use "
            "emojis. Return only the JSON object."
        ),
        inputs=inputs,
        max_completion_tokens=3500,
    )

    opportunities, recommendation = _coerce_opportunities(raw)
    if product_type and product_type != "Not Sure Yet":
        for opp in opportunities:
            opp["product_type"] = product_type
        recommendation["best_product_type"] = product_type
        recommendation["best_format"] = product_type

    payload = {
        "interest": interest,
        "audience": audience,
        "product_type": product_type or "Not Sure Yet",
        "difficulty": difficulty,
        "goal": goal,
        "mode": mode,
        "sources": sources,
        "opportunities": opportunities,
        "recommendation": recommendation,
    }
    err = ai_error or provider_error
    return attach_advantage(
        payload,
        inputs=inputs,
        sources=sources,
        live=live_used,
        ai_notes=[recommendation.get("why_selected") or ""] if recommendation.get("why_selected") else [],
        competition_level=(opportunities[0].get("competition") if opportunities else ""),
        competition_verified=False,
        competitors=[{"title": s.get("title"), "url": s.get("url"), "excerpt": s.get("excerpt"), "access_date": s.get("access_date")} for s in sources[:5]],
        search_terms=[k.strip() for k in (inputs.get("keywords") or "").split(",") if k.strip()],
        provider_error=err,
    )


def _clean_text(value) -> str:
    return str(value or "").strip()


def _is_any_audience(value: str) -> bool:
    return _clean_text(value).lower() in _ANY_AUDIENCE


def _is_any_type(value: str) -> bool:
    return _clean_text(value).lower() in _ANY_TYPE


def _is_any_platform(value: str) -> bool:
    return _clean_text(value).lower() in _ANY_PLATFORM


def _merge_sources(primary, extra) -> list:
    merged = []
    seen = set()
    for src in list(primary or []) + list(extra or []):
        if not isinstance(src, dict):
            continue
        url = _clean_text(src.get("url"))
        key = url or _clean_text(src.get("title"))
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        merged.append(src)
    return merged


def _as_platform_list(value) -> list[str]:
    if isinstance(value, list):
        return [_clean_text(item) for item in value if _clean_text(item)]
    text = _clean_text(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,;/]| and ", text) if part.strip()]


def _display_competition(raw: str) -> str:
    level = _clean_text(raw).lower()
    if level in {"low"}:
        return "Low"
    if level in {"medium", "moderate"}:
        return "Moderate"
    if level in {"high"}:
        return "High"
    return raw.strip() if _clean_text(raw) else "Not verified"


def _competition_level_for_score(raw: str) -> str:
    label = _display_competition(raw)
    if label == "Moderate":
        return "medium"
    return label.lower() if label in {"Low", "High"} else ""


def _source_blob(sources: list) -> str:
    parts = []
    for src in sources or []:
        if not isinstance(src, dict):
            continue
        parts.append(
            " ".join(
                _clean_text(src.get(key))
                for key in ("title", "url", "excerpt", "content")
            )
        )
    return " ".join(parts)


def _strip_unverified_bestseller(text: str, sources_text: str) -> str:
    value = _clean_text(text)
    if not value or not _BESTSELLER_RE.search(value):
        return value
    if _BESTSELLER_RE.search(sources_text or ""):
        return value
    return _BESTSELLER_RE.sub("popular listing", value)


def _discovery_search_subject(inputs: dict) -> str:
    parts = ["current digital product opportunities"]
    interest = _clean_text(inputs.get("interest") or inputs.get("topic"))
    audience = "" if _is_any_audience(inputs.get("audience")) else _clean_text(inputs.get("audience"))
    product_type = "" if _is_any_type(inputs.get("product_type")) else _clean_text(inputs.get("product_type"))
    platform = "" if _is_any_platform(inputs.get("sales_platform")) else _clean_text(inputs.get("sales_platform"))
    if interest:
        parts.append(interest)
    if audience:
        parts.append(f"for {audience}")
    if product_type:
        parts.append(product_type)
    if platform:
        parts.append(f"sold on {platform}")
    parts.append("public listings demand competition pricing")
    return " ".join(parts)


def _discovery_failure(inputs: dict, provider_error: str | None = None) -> dict:
    payload = {
        "error": DISCOVERY_FAILURE_MESSAGE,
        "inputs": inputs,
        "filters": inputs,
        "opportunities": [],
        "sources": [],
        "retryable": True,
        "generated": False,
        "auto_generated": False,
        "fma_mode": "discover",
        "workflow": "factory_market_advantage",
        "results_title": DISCOVERY_RESULTS_TITLE,
        "discovery_disclaimer": DISCOVERY_DISCLAIMER,
    }
    if provider_error:
        payload["provider_error"] = provider_error
    return payload


def _discovery_chat_json(system: str, user: str) -> tuple[dict, str | None]:
    """Extract opportunities from live research. Never invent a researched list."""
    try:
        raw = chat_json(system=system, user=user, max_completion_tokens=4000)
        if not isinstance(raw, dict):
            raw = {}
        return raw, None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Discovery research assistant failed: %s", exc, exc_info=True)
        return {}, AI_UNAVAILABLE_MESSAGE


def _score_discovered_opportunity(opp: dict, sources: list, live: bool, filter_inputs: dict) -> dict:
    platforms = _as_platform_list(opp.get("suggested_platforms") or opp.get("sales_platform"))
    platform = platforms[0] if platforms else filter_inputs.get("sales_platform") or ""
    if _is_any_platform(platform):
        platform = ""
    product_type = opp.get("product_type") or ""
    if _is_any_type(product_type):
        product_type = ""
    opp_inputs = collect_inputs(
        {
            "topic": opp.get("product_idea") or "",
            "audience": opp.get("target_audience") or filter_inputs.get("audience") or "",
            "customer_problem": opp.get("customer_problem") or "",
            "product_type": product_type or "Not Sure Yet",
            "sales_platform": platform or "Not sure",
            "target_price": opp.get("price_range") or "",
            "keywords": filter_inputs.get("keywords") or "",
            "expertise": filter_inputs.get("expertise") or "",
            "depth": filter_inputs.get("depth") or DEPTH_QUICK,
            "niche": opp.get("niche") or "",
            "interest": filter_inputs.get("interest") or "",
        }
    )
    opp_sources = _merge_sources(opp.get("sources"), sources)
    sourced = [normalize_source(src) for src in opp_sources]
    evidence = classify_evidence(sources=sourced, inputs=opp_inputs, live=live)
    evidence["competition_level"] = _competition_level_for_score(opp.get("competition"))
    evidence["competition_verified"] = bool(live and sourced and evidence["competition_level"])
    evidence["differentiation_count"] = 3 if opp.get("customer_problem") else 0
    evidence["researched_at"] = utc_today()
    evidence["fabricated_as_facts"] = False
    score = compute_factory_advantage(opp_inputs, evidence)
    row = dict(opp)
    row["factory_advantage"] = score
    row["opportunity_score"] = score["total"]
    row["factory_advantage_total"] = score["total"]
    row["evidence"] = evidence
    row["sources"] = sourced
    row["compact_evidence"] = compact_evidence_summary(row, score)
    return row


def _rank_evidence_backed(raw: dict, sources: list, inputs: dict, live: bool) -> list[dict]:
    items = raw.get("opportunities") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        items = []
    sources_text = _source_blob(sources)
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        idea = _clean_text(item.get("product_idea") or item.get("idea"))
        if not idea:
            continue
        demand = _clean_text(item.get("demand_evidence"))
        why = _clean_text(item.get("why_opportunity") or item.get("why_this_exists"))
        opp_sources = item.get("sources") if isinstance(item.get("sources"), list) else []
        if not demand and not why and not opp_sources:
            continue
        if not demand:
            demand = why
        linked = _merge_sources(opp_sources, sources)
        if not live and not linked:
            continue
        preferred_type = "" if _is_any_type(inputs.get("product_type")) else normalize_product_type(
            inputs.get("product_type") or ""
        )
        product_type = preferred_type or normalize_product_type(item.get("product_type") or "")
        if product_type == "Not Sure Yet" and not preferred_type:
            product_type = _clean_text(item.get("product_type")) or "Not Sure Yet"
        platforms = _as_platform_list(item.get("suggested_platforms") or item.get("sales_platforms"))
        if not platforms and not _is_any_platform(inputs.get("sales_platform")):
            platforms = [_clean_text(inputs.get("sales_platform"))]
        price = _strip_unverified_bestseller(
            _clean_text(item.get("price_range")) or "Not verified",
            sources_text,
        )
        if not _clean_text(item.get("price_range")):
            price = "Not verified"
        why = reject_unsupported_trend_language(
            _strip_unverified_bestseller(
                _clean_text(item.get("why_opportunity") or item.get("why_this_exists")),
                sources_text,
            )
        )
        why_sell = reject_unsupported_trend_language(
            _strip_unverified_bestseller(
                _clean_text(item.get("why_it_could_sell") or item.get("sales_angle") or why),
                sources_text,
            )
        )
        demand_ev = reject_unsupported_trend_language(
            _strip_unverified_bestseller(demand, sources_text)
        )
        opp = {
            "niche": _clean_text(item.get("niche") or inputs.get("interest") or idea),
            "product_idea": idea,
            "product_type": product_type,
            "target_audience": _clean_text(item.get("target_audience") or item.get("target_customer") or inputs.get("audience")),
            "customer_problem": _clean_text(item.get("customer_problem")),
            "why_opportunity": why,
            "demand_evidence": demand_ev,
            "competition": _display_competition(item.get("competition")),
            "competition_explanation": _clean_text(item.get("competition_explanation") or item.get("competition_why")),
            "price_range": price,
            "suggested_platforms": platforms,
            "why_it_could_sell": why_sell,
            "main_risk": _clean_text(item.get("main_risk")),
            "sales_angle": why_sell,
            "difficulty": _clean_text(item.get("difficulty")),
            "sources": linked,
        }
        scored = _score_discovered_opportunity(opp, linked, live, inputs)
        cleaned.append(scored)

    cleaned.sort(key=lambda row: int(row.get("opportunity_score") or 0), reverse=True)
    ranked = cleaned[:DISCOVERY_MAX]
    for idx, opp in enumerate(ranked, start=1):
        opp["rank"] = idx
    return ranked


def discover_top_opportunities(
    interest: str = "",
    audience: str = "",
    product_type: str = "",
    sales_platform: str = "",
    depth: str = "",
    **kwargs,
) -> dict:
    """Rank up to 10 evidence-backed opportunities using the existing research stack.

    Does not invent demand, revenue, sales, or bestseller status. If live research
    cannot support any opportunity, returns a retryable failure and preserves filters.
    Never pads the list to 10.
    """
    body = {
        "interest": interest,
        "audience": "" if _is_any_audience(audience) else audience,
        "product_type": product_type,
        "sales_platform": sales_platform,
        "depth": depth or DEPTH_QUICK,
        "topic": kwargs.get("topic") or interest,
        "customer_problem": kwargs.get("customer_problem") or "",
        "keywords": kwargs.get("keywords") or "",
        "expertise": kwargs.get("expertise") or "",
        "target_price": kwargs.get("target_price") or "",
        "niche": kwargs.get("niche") or "",
        "goal": kwargs.get("goal") or "",
        "difficulty": kwargs.get("difficulty") or "",
    }
    if not _clean_text(body.get("depth")):
        body["depth"] = DEPTH_QUICK
    inputs = collect_inputs(body)
    if not _clean_text(depth) and not _clean_text(kwargs.get("depth")):
        inputs["depth"] = DEPTH_QUICK
    if _is_any_audience(inputs.get("audience")):
        inputs["audience"] = ""
    if _is_any_type(inputs.get("product_type")):
        inputs["product_type"] = "Not Sure Yet"
    if _is_any_platform(inputs.get("sales_platform")):
        inputs["sales_platform"] = "Not sure"
    inputs["fma_mode"] = "discover"
    inputs["interest"] = _clean_text(interest or inputs.get("interest"))

    search_subject = _discovery_search_subject(inputs)
    live_used, context, sources, provider_error = _tavily_context(
        search_subject,
        inputs.get("audience") or "",
        depth=inputs.get("depth") or DEPTH_QUICK,
    )
    sources = _merge_sources(sources, kwargs.get("carried_sources"))
    if not live_used or not sources:
        return _discovery_failure(inputs, provider_error)

    type_clause = (
        f'Preferred product type: {inputs["product_type"]}. Keep this exact type. Do not convert it to Ebook.'
        if not _is_any_type(inputs.get("product_type"))
        else "Product type is open. Recommend a Factory-buildable type supported by the sources."
    )
    audience_clause = (
        f'Preferred audience: {inputs["audience"]}.'
        if inputs.get("audience")
        else "Audience is open."
    )
    interest_clause = (
        f'Interest / niche hint: {inputs["interest"]}.'
        if inputs.get("interest")
        else "No interest filter was provided."
    )
    platform_clause = (
        f'Preferred sales platform: {inputs["sales_platform"]}.'
        if not _is_any_platform(inputs.get("sales_platform"))
        else "Sales platform is open."
    )
    source_block = context[:14000] if context else ""

    raw, ai_error = _discovery_chat_json(
        system=(
            "You extract digital-product opportunities from live public web research. "
            "You never invent demand, revenue, unit sales, ratings, search volume, "
            "BSR, or marketplace performance. You never call something a verified "
            "best seller unless a provided source establishes that claim. "
            "Return fewer items when evidence is thin. Do not pad the list."
        ),
        user=(
            "Extract specific digital-product opportunities supported by the live "
            "research below. Each item must be a concrete product idea, not a broad niche.\n\n"
            f"FILTERS:\n- {audience_clause}\n- {type_clause}\n- {platform_clause}\n"
            f"- {interest_clause}\n- Research depth: {inputs.get('depth')}\n\n"
            f"LIVE WEB RESEARCH:\n{source_block}\n\n"
            "Return a JSON object with key \"opportunities\": an array of UP TO 10 "
            "objects. Fewer is required when evidence does not support 10. "
            "Each object must have: product_idea, product_type, target_audience, "
            "customer_problem, why_opportunity, demand_evidence, competition "
            "(Low, Moderate, or High), competition_explanation, price_range "
            "(public listings only, or \"Not verified\"), suggested_platforms "
            "(array), why_it_could_sell, main_risk, sources (array of "
            "{title, url} copied from the research). "
            "Do not invent metrics. Do not use emojis. Return only JSON."
        ),
    )
    opportunities = _rank_evidence_backed(raw, sources, inputs, live_used)
    if not opportunities:
        return _discovery_failure(inputs, ai_error or provider_error)

    top = opportunities[0]
    recommendation = {
        "best_niche": top.get("niche") or "",
        "best_product": top.get("product_idea") or "",
        "best_product_type": top.get("product_type") or "",
        "why_selected": top.get("why_opportunity") or "",
        "best_format": top.get("product_type") or "",
        "suggested_title": top.get("product_idea") or "",
        "next_step": "Research This Idea, then Choose Your Advantage.",
    }
    payload = {
        "interest": inputs.get("interest") or "",
        "audience": inputs.get("audience") or "",
        "product_type": inputs.get("product_type") or "Not Sure Yet",
        "sales_platform": inputs.get("sales_platform") or "Not sure",
        "difficulty": inputs.get("difficulty") or "",
        "goal": inputs.get("goal") or "",
        "mode": "live" if live_used else "ai_estimated",
        "sources": sources,
        "opportunities": opportunities,
        "recommendation": recommendation,
        "fma_mode": "discover",
        "results_title": DISCOVERY_RESULTS_TITLE,
        "discovery_disclaimer": DISCOVERY_DISCLAIMER,
        "generated": False,
        "auto_generated": False,
        "filters": inputs,
    }
    attached = attach_advantage(
        payload,
        inputs=inputs,
        sources=sources,
        live=live_used,
        ai_notes=[top.get("why_opportunity") or ""] if top.get("why_opportunity") else [],
        competition_level=top.get("competition") or "",
        competition_verified=False,
        competitors=[
            {
                "title": src.get("title"),
                "url": src.get("url"),
                "excerpt": src.get("excerpt"),
                "access_date": src.get("access_date"),
            }
            for src in sources[:5]
        ],
        search_terms=[k.strip() for k in (inputs.get("keywords") or "").split(",") if k.strip()],
        provider_error=ai_error or provider_error,
    )
    attached["fma_mode"] = "discover"
    attached["results_title"] = DISCOVERY_RESULTS_TITLE
    attached["discovery_disclaimer"] = DISCOVERY_DISCLAIMER
    attached["generated"] = False
    attached["auto_generated"] = False
    attached["opportunities"] = opportunities
    return attached


def _coerce_report(raw: dict) -> dict:
    """Normalise the AI output so the frontend always gets every field."""
    report = {}
    for key in _REPORT_KEYS:
        report[key] = raw.get(key, "")
    # Normalise list-typed fields to lists.
    for key in ("customer_problems", "search_terms", "product_ideas", "title_ideas"):
        val = report.get(key)
        if isinstance(val, str):
            report[key] = [val] if val.strip() else []
        elif not isinstance(val, list):
            report[key] = []
    # Clamp opportunity score to 1-100.
    try:
        score = int(round(float(report.get("opportunity_score") or 0)))
    except (TypeError, ValueError):
        score = 0
    report["opportunity_score"] = max(1, min(100, score)) if score else 0
    return report


def market_research(niche: str, audience: str, product_type: str, **kwargs) -> dict:
    niche = (niche or "").strip()
    audience = (audience or "").strip()
    product_type = (product_type or "").strip() or "Not Sure Yet"
    if not niche:
        raise ValueError("Please enter a niche or keyword to research.")

    body = {
        "niche": niche,
        "topic": kwargs.get("topic") or niche,
        "audience": audience,
        "product_type": product_type,
        **kwargs,
    }
    inputs = collect_inputs(body)
    product_type = inputs["product_type"]

    live_used, context, sources, provider_error = _tavily_context(
        niche, audience, depth=inputs.get("depth") or ""
    )
    mode = "live" if live_used else "ai_estimated"

    if context:
        source_clause = (
            "Base your analysis on the live web research provided below. "
            f"\n\nLIVE WEB RESEARCH:\n{context[:14000]}"
        )
    else:
        source_clause = (
            "No live web data is available, so produce your best expert estimate "
            "based on general market knowledge. Do not invent search volume, BSR, "
            "revenue, or review counts."
        )

    format_clause = (
        "The user has not chosen a format yet, so recommend the best one."
        if product_type == "Not Sure Yet"
        else (
            f"The user is considering this product format: {product_type}. "
            "Keep that format. Do not convert it to Ebook."
        )
    )

    raw, ai_error = _safe_chat_json(
        system=(
            "You are a digital-product market research analyst who helps "
            "beginners find profitable, low-overhead digital products to create. "
            "You are concrete, realistic, and encouraging. Never invent search "
            "volume, BSR, sales, revenue, or review counts."
        ),
        user=(
            f'Produce a market opportunity report for the niche "{niche}"'
            + (f' targeting "{audience}"' if audience else "")
            + f". {format_clause} {source_clause}\n\n"
            "Return a JSON object with EXACTLY these keys:\n"
            '- "niche_summary": string, 2-3 sentences.\n'
            '- "target_audience": string describing who this is for.\n'
            '- "customer_problems": array of 3-6 short strings.\n'
            '- "search_terms": array of 4-8 short search phrases people may use.\n'
            '- "product_ideas": array of 3-6 specific digital product ideas.\n'
            '- "best_format": string, the single best product format and why.\n'
            '- "title_ideas": array of 3-6 catchy product title strings.\n'
            '- "price_range": string, e.g. "$9 - $19" or "Not verified".\n'
            '- "difficulty": string, one of "Easy", "Medium", "Hard".\n'
            '- "competition": string, one of "Low", "Medium", "High".\n'
            '- "opportunity_score": integer from 1 to 100.\n'
            '- "why_worth_creating": string, 2-3 sentences.\n'
            '- "next_step": string, one clear recommended next action.\n'
            "Do not use emojis. Return only the JSON object."
        ),
        inputs=inputs,
        max_completion_tokens=3000,
    )

    if raw.get("opportunities"):
        opportunities, recommendation = _coerce_opportunities(raw)
        report = _coerce_report(raw)
    else:
        report = _coerce_report(raw)
        ideas = report.get("product_ideas") or [niche]
        opportunities = [
            {
                "niche": niche,
                "product_idea": str(idea),
                "product_type": product_type if product_type != "Not Sure Yet" else (report.get("best_format") or "Ebook"),
                "target_audience": report.get("target_audience") or audience,
                "customer_problem": (report.get("customer_problems") or [inputs.get("customer_problem")])[0]
                if (report.get("customer_problems") or inputs.get("customer_problem"))
                else "",
                "why_opportunity": report.get("why_worth_creating") or "",
                "price_range": report.get("price_range") or inputs.get("target_price") or "",
                "difficulty": report.get("difficulty") or "",
                "competition": report.get("competition") or "",
                "opportunity_score": report.get("opportunity_score") or 0,
                "sales_angle": "",
            }
            for idea in ideas[:5]
        ]
        if not opportunities:
            opportunities, recommendation = _coerce_opportunities(_offline_raw(inputs))
        else:
            if product_type and product_type != "Not Sure Yet":
                for opp in opportunities:
                    opp["product_type"] = product_type
            top = opportunities[0]
            recommendation = {
                "best_niche": niche,
                "best_product": top["product_idea"],
                "best_product_type": top["product_type"],
                "why_selected": report.get("why_worth_creating") or "",
                "best_format": product_type if product_type != "Not Sure Yet" else (report.get("best_format") or top["product_type"]),
                "suggested_title": (report.get("title_ideas") or [top["product_idea"]])[0],
                "next_step": report.get("next_step") or "Choose Your Advantage",
            }

    if product_type and product_type != "Not Sure Yet":
        for opp in opportunities:
            opp["product_type"] = product_type
        recommendation["best_product_type"] = product_type
        recommendation["best_format"] = product_type

    payload = {
        "niche": niche,
        "audience": audience,
        "product_type": product_type,
        "mode": mode,
        "sources": sources,
        "report": report,
        "opportunities": opportunities,
        "recommendation": recommendation,
    }
    return attach_advantage(
        payload,
        inputs=inputs,
        sources=sources,
        live=live_used,
        ai_notes=[report.get("why_worth_creating") or ""] if report.get("why_worth_creating") else [],
        competition_level=report.get("competition") or "",
        competition_verified=False,
        competitors=[{"title": s.get("title"), "url": s.get("url"), "excerpt": s.get("excerpt"), "access_date": s.get("access_date")} for s in sources[:5]],
        search_terms=list(report.get("search_terms") or []),
        provider_error=ai_error or provider_error,
    )
