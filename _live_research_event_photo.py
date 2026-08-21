"""Research-only stage for live ebook acceptance. Do not write manuscript/cover."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from tavily import TavilyClient

from ai_client import MODEL, chat_json

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

OUT = ROOT / "exports" / "ebook_live_acceptance_lonnie_event_photo"
OUT.mkdir(parents=True, exist_ok=True)

TOPIC = "How to Start a Profitable Event Photography Business with On-Site Photo Printing"
AUDIENCE = (
    "Beginner and intermediate photographers who want to earn money at weddings, "
    "parties, school events, church events, reunions, and community celebrations."
)
OUTCOME = (
    "Give readers a practical step-by-step plan for choosing equipment, creating "
    "service packages, setting profitable prices, booking clients, managing an event, "
    "printing photographs and keepsakes on-site, avoiding common mistakes, and "
    "securing their first paid event."
)
AUTHOR = "Lonnie Brown"
BUDGET_CAP = 3.50
RESEARCH_BUDGET = 0.50

TAVILY_CREDIT_USD = 0.008
TAVILY_ADVANCED_CREDITS = 2
OPENAI_SYNTHESIS_EST_USD = 0.35

ledger: dict = {
    "run_id": "ebook_live_acceptance_event_photo_20260811",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "budget_cap_usd": BUDGET_CAP,
    "research_budget_usd": RESEARCH_BUDGET,
    "author": AUTHOR,
    "topic": TOPIC,
    "audience": AUDIENCE,
    "outcome": OUTCOME,
    "calls": [],
    "totals": {"estimated_usd": 0.0, "paid_calls": 0},
    "rules": [
        "Do not invent personal stories, earnings, clients, credentials, or quotations attributed to Lonnie Brown.",
        "Cover/image spend blocked until manuscript and outline are approved.",
        "Pause at every checkpoint; approval of one stage does not authorize later stages.",
    ],
}


def add_call(provider: str, purpose: str, est_usd: float, meta: dict | None = None) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "purpose": purpose,
        "estimated_cost_usd": round(est_usd, 4),
        "meta": meta or {},
    }
    ledger["calls"].append(entry)
    ledger["totals"]["estimated_usd"] = round(
        sum(float(c["estimated_cost_usd"]) for c in ledger["calls"]), 4
    )
    ledger["totals"]["paid_calls"] = len(ledger["calls"])
    if ledger["totals"]["estimated_usd"] > BUDGET_CAP:
        raise RuntimeError(
            f"Budget cap exceeded: {ledger['totals']['estimated_usd']} > {BUDGET_CAP}"
        )


def main() -> None:
    key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("TAVILY_API_KEY missing")

    client = TavilyClient(api_key=key)
    queries = [
        (
            "event photography business startup equipment packages pricing checklist for beginners",
            "Core business setup, equipment, packages, and pricing signals",
        ),
        (
            "on-site photo printing event photography portable printer workflow keepsakes costs",
            "On-site printing workflow, printers, keepsakes, and ops costs",
        ),
    ]

    raw_searches: list[dict] = []
    for q, purpose in queries:
        est = TAVILY_ADVANCED_CREDITS * TAVILY_CREDIT_USD
        if ledger["totals"]["estimated_usd"] + est > RESEARCH_BUDGET:
            raise RuntimeError("Would exceed research budget before Tavily call")
        t0 = time.time()
        search = client.search(
            query=q,
            search_depth="advanced",
            max_results=8,
            include_answer=True,
        )
        elapsed = round(time.time() - t0, 2)
        results = [
            {
                "title": r.get("title", "Untitled"),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
            }
            for r in (search.get("results") or [])
        ]
        add_call(
            "Tavily",
            purpose,
            est,
            {
                "endpoint": "search",
                "search_depth": "advanced",
                "credits": TAVILY_ADVANCED_CREDITS,
                "query": q,
                "result_count": len(results),
                "elapsed_sec": elapsed,
                "model_notes": "2 credits advanced search @ $0.008/credit PAYG reference",
            },
        )
        raw_searches.append(
            {
                "query": q,
                "purpose": purpose,
                "answer": search.get("answer") or "",
                "results": results,
            }
        )

    blocks: list[str] = []
    for block in raw_searches:
        if block["answer"]:
            blocks.append(f"Web summary ({block['purpose']}): {block['answer']}")
        for r in block["results"]:
            blocks.append(f"Source: {r['title']} ({r['url']})\n{r['content']}")
    context = "\n\n".join(blocks)[:14000]

    if ledger["totals"]["estimated_usd"] + OPENAI_SYNTHESIS_EST_USD > BUDGET_CAP:
        raise RuntimeError("Synthesis would exceed total budget cap")

    t0 = time.time()
    brief = chat_json(
        system=(
            "You are a careful research analyst preparing notes for a practical ebook. "
            "Use only the provided live web research. Do not invent statistics, vendors, "
            "prices, laws, or case studies that are not supported by the sources. "
            "If evidence is thin, say so explicitly. "
            "Never invent personal stories, earnings, clients, credentials, or quotations "
            f"attributed to {AUTHOR}. Author name may appear only as the listed author field."
        ),
        user=(
            f"AUTHOR (listed only, invent nothing about them): {AUTHOR}\n"
            f"TOPIC: {TOPIC}\n"
            f"AUDIENCE: {AUDIENCE}\n"
            f"READER OUTCOME: {OUTCOME}\n\n"
            f"LIVE WEB RESEARCH:\n{context}\n\n"
            "Return JSON with EXACTLY these keys:\n"
            '- "research_summary": string (8-14 sentences, practical, no personal anecdotes about the author)\n'
            '- "key_findings": array of 8-12 short strings grounded in sources\n'
            '- "equipment_notes": array of strings\n'
            '- "pricing_and_packages_notes": array of strings (flag uncertainty)\n'
            '- "event_ops_and_onsite_printing_notes": array of strings\n'
            '- "common_mistakes_and_risks": array of strings\n'
            '- "first_paid_event_checklist_candidates": array of strings\n'
            '- "open_questions": array of strings\n'
            '- "source_urls_used": array of strings\n'
            '- "suggested_working_title": string\n'
            '- "suggested_subtitle": string\n'
            '- "proposed_outline_angles": array of 7-10 chapter angle strings '
            "(for later outline approval only; do not write chapters)\n"
            "Do not use emojis. Do not fabricate Lonnie Brown biography or testimonials."
        ),
        max_completion_tokens=3500,
    )
    elapsed = round(time.time() - t0, 2)
    add_call(
        "OpenAI-compatible (AI_INTEGRATIONS)",
        "Synthesize research brief for acceptance ebook (no manuscript)",
        OPENAI_SYNTHESIS_EST_USD,
        {
            "model": MODEL,
            "max_completion_tokens": 3500,
            "elapsed_sec": elapsed,
            "estimate_basis": "conservative flat estimate for gpt-5.4 synthesis under proxy",
        },
    )

    payload = {
        "stage": "research_only",
        "status": "AWAITING_HUMAN_REVIEW",
        "author": AUTHOR,
        "topic": TOPIC,
        "audience": AUDIENCE,
        "outcome": OUTCOME,
        "research_brief": brief,
        "raw_searches": raw_searches,
        "ledger": ledger,
        "next_checkpoint": "Approve or edit research brief before title/outline stages",
        "blocked_until_approval": [
            "title options",
            "outline",
            "manuscript",
            "visuals",
            "cover/image spend",
            "preflight",
            "save/export",
        ],
    }

    (OUT / "paid_call_ledger.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    (OUT / "research_brief.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    notes: list[str] = [
        f"# Research Brief — {TOPIC}",
        f"Author (listed only): {AUTHOR}",
        f"Audience: {AUDIENCE}",
        f"Outcome: {OUTCOME}",
        "",
        "## Working title / subtitle suggestions",
        str(brief.get("suggested_working_title") or ""),
        str(brief.get("suggested_subtitle") or ""),
        "",
        "## Research summary",
        str(brief.get("research_summary") or ""),
        "",
        "## Key findings",
    ]
    for x in brief.get("key_findings") or []:
        notes.append(f"- {x}")
    notes += ["", "## Equipment notes"]
    for x in brief.get("equipment_notes") or []:
        notes.append(f"- {x}")
    notes += ["", "## Pricing and packages notes"]
    for x in brief.get("pricing_and_packages_notes") or []:
        notes.append(f"- {x}")
    notes += ["", "## Event ops / on-site printing"]
    for x in brief.get("event_ops_and_onsite_printing_notes") or []:
        notes.append(f"- {x}")
    notes += ["", "## Common mistakes and risks"]
    for x in brief.get("common_mistakes_and_risks") or []:
        notes.append(f"- {x}")
    notes += ["", "## First paid event checklist candidates"]
    for x in brief.get("first_paid_event_checklist_candidates") or []:
        notes.append(f"- {x}")
    notes += ["", "## Open questions"]
    for x in brief.get("open_questions") or []:
        notes.append(f"- {x}")
    notes += ["", "## Proposed outline angles (NOT approved yet)"]
    for x in brief.get("proposed_outline_angles") or []:
        notes.append(f"- {x}")
    notes += ["", "## Sources used"]
    for u in brief.get("source_urls_used") or []:
        notes.append(f"- {u}")
    notes += [
        "",
        "## Paid-call ledger (estimate)",
        f"Total estimated USD so far: {ledger['totals']['estimated_usd']}",
        f"Remaining under ${BUDGET_CAP:.2f} cap: {round(BUDGET_CAP - ledger['totals']['estimated_usd'], 4)}",
    ]
    for c in ledger["calls"]:
        notes.append(
            f"- {c['provider']}: {c['purpose']} — est ${c['estimated_cost_usd']:.4f}"
        )

    (OUT / "research_brief.md").write_text("\n".join(notes), encoding="utf-8")
    print("OK")
    print("EST_TOTAL", ledger["totals"]["estimated_usd"])
    print("CALLS", ledger["totals"]["paid_calls"])
    print("OUT", OUT)


if __name__ == "__main__":
    main()
