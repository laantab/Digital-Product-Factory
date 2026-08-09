"""Market Research module.

Produces a structured "opportunity report" for a niche/audience/product-type.
Uses live Tavily web search when TAVILY_API_KEY is set; otherwise falls back to
an AI-estimated report that is clearly labelled as such.
"""
import logging
import os

from ai_client import chat_json

logger = logging.getLogger(__name__)

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


def _tavily_context(niche: str, audience: str) -> tuple[bool, str, list[dict]]:
    """Return (live_used, context_text, sources).

    Fails open: if Tavily is missing OR errors out, returns live_used=False so the
    caller falls back to AI-estimated research instead of raising.
    """
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return False, "", []
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=key)
        query = (
            f"demand, audience and competition for {niche} digital products"
            + (f" for {audience}" if audience else "")
        )
        search = client.search(
            query=query, search_depth="advanced", max_results=8, include_answer=True
        )
    except Exception:  # noqa: BLE001
        logger.warning("Tavily search failed; falling back to AI-estimated research", exc_info=True)
        return False, "", []

    sources = [
        {
            "title": r.get("title", "Untitled"),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
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
    return True, context, sources


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


def discover_products(
    interest: str,
    audience: str,
    product_type: str,
    difficulty: str,
    goal: str,
    niche: str = "",
) -> dict:
    """Ranked product opportunities + a single best recommendation.

    Powers both Market Research paths:
    - Path 1 ("I already have a niche"): ``niche`` is set, so every opportunity
      must stay INSIDE that niche.
    - Path 2 ("Find the best niche for me"): ``niche`` is empty and the analysis
      explores broadly from an optional ``interest`` area.
    Everything else is an optional preference.
    """
    interest = (interest or "").strip()
    audience = (audience or "").strip()
    product_type = (product_type or "").strip()
    difficulty = (difficulty or "").strip()
    goal = (goal or "").strip()
    niche = (niche or "").strip()

    # Prefer the explicit niche for live research; otherwise use the broad interest.
    search_subject = niche or interest
    live_used, context, sources = (False, "", [])
    if search_subject:
        live_used, context, sources = _tavily_context(search_subject, audience)
    mode = "live" if live_used else "ai_estimated"

    if context:
        source_clause = (
            "Base your analysis on the live web research provided below.\n\n"
            f"LIVE WEB RESEARCH:\n{context[:14000]}"
        )
    else:
        source_clause = (
            "No live web data is available, so produce your best expert estimate "
            "based on general market knowledge."
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
        prefs.append(f"Preferred product type: {product_type}")
    if difficulty:
        prefs.append(f"Preferred difficulty level: {difficulty}")
    if goal:
        prefs.append(f"User's goal: {goal}")
    prefs_block = "\n".join(f"- {p}" for p in prefs)

    raw = chat_json(
        system=(
            "You are a digital-product market research analyst who helps "
            "beginners decide what to build. You compare several options and "
            "commit to a single clear recommendation. You are concrete, "
            "realistic, and encouraging."
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
            'e.g. "$9 - $19"), "difficulty" (one of "Easy", "Medium", "Hard"), '
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
        max_completion_tokens=3500,
    )

    opportunities, recommendation = _coerce_opportunities(raw)
    return {
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


def market_research(niche: str, audience: str, product_type: str) -> dict:
    niche = (niche or "").strip()
    audience = (audience or "").strip()
    product_type = (product_type or "").strip() or "Not Sure Yet"
    if not niche:
        raise ValueError("Please enter a niche or keyword to research.")

    live_used, context, sources = _tavily_context(niche, audience)
    mode = "live" if live_used else "ai_estimated"

    if context:
        source_clause = (
            "Base your analysis on the live web research provided below. "
            f"\n\nLIVE WEB RESEARCH:\n{context[:14000]}"
        )
    else:
        source_clause = (
            "No live web data is available, so produce your best expert estimate "
            "based on general market knowledge."
        )

    format_clause = (
        "The user has not chosen a format yet, so recommend the best one."
        if product_type == "Not Sure Yet"
        else f"The user is considering this product format: {product_type}."
    )

    raw = chat_json(
        system=(
            "You are a digital-product market research analyst who helps "
            "beginners find profitable, low-overhead digital products to create. "
            "You are concrete, realistic, and encouraging."
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
            '- "price_range": string, e.g. "$9 - $19".\n'
            '- "difficulty": string, one of "Easy", "Medium", "Hard".\n'
            '- "competition": string, one of "Low", "Medium", "High".\n'
            '- "opportunity_score": integer from 1 to 100.\n'
            '- "why_worth_creating": string, 2-3 sentences.\n'
            '- "next_step": string, one clear recommended next action.\n'
            "Do not use emojis. Return only the JSON object."
        ),
        max_completion_tokens=3000,
    )

    report = _coerce_report(raw)
    return {
        "niche": niche,
        "audience": audience,
        "product_type": product_type,
        "mode": mode,
        "sources": sources,
        "report": report,
    }
