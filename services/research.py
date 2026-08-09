"""Niche Research workflow.

Runs one live Tavily web search for a keyword, returns the raw search results,
then turns that research into a ranked list of digital-product opportunities plus
a single best recommendation (the same shape the Market Research discovery flow
uses, so the frontend can share renderers and the Choose/Use buttons).
"""
import logging
import os

from tavily import TavilyClient

from ai_client import chat_json
from services.market_research import _coerce_opportunities

logger = logging.getLogger(__name__)


def _tavily() -> TavilyClient:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        raise RuntimeError(
            "TAVILY_API_KEY is not set. Add it in the Secrets tab to enable research."
        )
    return TavilyClient(api_key=key)


def research(keyword: str) -> dict:
    keyword = (keyword or "").strip()
    if not keyword:
        raise ValueError("Please enter a keyword to research.")

    client = _tavily()
    search = client.search(
        query=f"trending profitable digital product niches and demand for {keyword}",
        search_depth="advanced",
        max_results=8,
        include_answer=True,
    )

    results = [
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
        f"Source: {r['title']} ({r['url']})\n{r['content']}" for r in results
    )

    raw = chat_json(
        system=(
            "You are a digital-product market analyst. You turn live web research "
            "into specific, profitable digital-product opportunities (ebooks, "
            "workbooks, printables, templates, courses). Be concrete and realistic."
        ),
        user=(
            f'Analyze the live web research below about "{keyword}" and identify the '
            "5 strongest digital-product opportunities, then pick the single best "
            "one to build.\n\n"
            f"RESEARCH:\n{context or 'No live web data was available; use your best expert estimate.'}\n\n"
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
        "keyword": keyword,
        "mode": "live" if results else "ai_estimated",
        "answer": answer,
        # Section 1 on the page; "results" kept as a backward-compatible alias.
        "raw_search_results": results,
        "results": results,
        # Sections 2 and 3.
        "recommended_product_opportunities": opportunities,
        "best_recommendation": recommendation,
        # Also expose under the discovery flow's key names so the frontend can
        # treat this payload exactly like a discovery result.
        "opportunities": opportunities,
        "recommendation": recommendation,
    }
