"""Niche Research workflow.

Runs one live Tavily web search for a keyword, returns the raw search results,
then turns that research into a ranked list of digital-product opportunities plus
a single best recommendation (the same shape the Market Research discovery flow
uses, so the frontend can share renderers and the Choose/Use buttons).

Factory Market Advantage is attached onto this existing payload. The /research
route is preserved.
"""
import logging
import os

from services.factory_advantage import collect_inputs
from services.market_research import discover_products

logger = logging.getLogger(__name__)


def _tavily():
    """Kept for backward-compatible imports. Live calls go through market_research."""
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        raise RuntimeError(
            "TAVILY_API_KEY is not set. Add it in the Secrets tab to enable research."
        )
    from tavily import TavilyClient

    return TavilyClient(api_key=key)


def research(keyword: str, **kwargs) -> dict:
    keyword = (keyword or "").strip()
    if not keyword:
        raise ValueError("Please enter a keyword to research.")

    body = {"keyword": keyword, "topic": kwargs.get("topic") or keyword, "interest": keyword, **kwargs}
    inputs = collect_inputs(body)
    payload = discover_products(
        interest=inputs["interest"] or keyword,
        audience=inputs["audience"],
        product_type=inputs["product_type"],
        difficulty=inputs["difficulty"],
        goal=inputs["goal"],
        niche=inputs["niche"],
        topic=inputs["topic"] or keyword,
        customer_problem=inputs["customer_problem"],
        sales_platform=inputs["sales_platform"],
        expertise=inputs["expertise"],
        target_price=inputs["target_price"],
        keywords=inputs["keywords"],
        depth=inputs["depth"],
    )
    results = list(payload.get("sources") or [])
    opportunities = payload.get("opportunities") or []
    recommendation = payload.get("recommendation") or {}
    payload.update(
        {
            "keyword": keyword,
            "answer": "",
            "raw_search_results": results,
            "results": results,
            "recommended_product_opportunities": opportunities,
            "best_recommendation": recommendation,
        }
    )
    return payload
