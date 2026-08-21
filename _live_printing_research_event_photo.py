"""Additional on-site printing research for live ebook acceptance. Research only."""
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

LEDGER_PATH = OUT / "paid_call_ledger.json"
BRIEF_PATH = OUT / "research_brief.json"

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

TAVILY_CREDIT_USD = 0.008
TAVILY_ADVANCED_CREDITS = 2
OPENAI_SYNTHESIS_EST_USD = 0.45  # slightly larger synthesis for denser printing brief


def load_ledger() -> dict:
    if LEDGER_PATH.is_file():
        return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    raise RuntimeError("Missing paid_call_ledger.json — run research stage first.")


def add_call(ledger: dict, provider: str, purpose: str, est_usd: float, meta: dict | None = None) -> None:
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
    ledger = load_ledger()
    prior = json.loads(BRIEF_PATH.read_text(encoding="utf-8")) if BRIEF_PATH.is_file() else {}

    key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("TAVILY_API_KEY missing")
    client = TavilyClient(api_key=key)

    queries = [
        (
            "site:dnpphoto.com OR site:dnpimagingcomm.com DS-RX1HS OR QW410 dye sublimation printer specifications print speed media cost",
            "DNP dye-sub event printer manufacturer specs / media",
        ),
        (
            "site:mitsubishi-imaging.com OR site:mitsubishielectric.com CP-D70DW OR CP-D90DW dye sublimation printer specifications print speed",
            "Mitsubishi dye-sub printer manufacturer specs",
        ),
        (
            "site:ciaat.com OR site:ciaatphoto.com OR site:hiTi.com OR site:hitiprinter.com dye sublimation photo printer event specifications media",
            "Other manufacturer dye-sub / event printer docs",
        ),
        (
            "event photo booth dye sublimation printer cost per print media ribbon paper pack pricing RX1HS QW410",
            "Cost-per-print and media pack pricing signals",
        ),
        (
            "event photography on-site printing workflow tether laptop print queue payment pickup file naming",
            "Laptop/tether/print-queue/payment/pickup workflow (practitioner)",
        ),
        (
            "on-site event photo keepsakes mug button plate shirt dye sublimation what can print during event vs post event",
            "Keepsakes realism: during-event vs post-event production",
        ),
    ]

    raw_searches: list[dict] = []
    for q, purpose in queries:
        est = TAVILY_ADVANCED_CREDITS * TAVILY_CREDIT_USD
        if ledger["totals"]["estimated_usd"] + est > BUDGET_CAP:
            raise RuntimeError("Would exceed budget before Tavily call")
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
            ledger,
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
    context = "\n\n".join(blocks)[:16000]

    if ledger["totals"]["estimated_usd"] + OPENAI_SYNTHESIS_EST_USD > BUDGET_CAP:
        raise RuntimeError("Synthesis would exceed total budget cap")

    t0 = time.time()
    printing_brief = chat_json(
        system=(
            "You are a careful technical research analyst. Use ONLY the provided live "
            "web research. Prefer manufacturer documentation over blogs when both exist. "
            "Clearly separate manufacturer-supported facts from practitioner recommendations. "
            "If a figure is missing, say 'not found in provided sources' — never invent "
            "speeds, prices, capacities, margins, or model claims. "
            f"Never invent personal stories, earnings, clients, credentials, or quotations "
            f"attributed to {AUTHOR}."
        ),
        user=(
            f"AUTHOR (listed only): {AUTHOR}\n"
            f"TOPIC: {TOPIC}\n"
            f"AUDIENCE: {AUDIENCE}\n"
            f"OUTCOME: {OUTCOME}\n\n"
            "Focus: on-site photo printing for event photography businesses.\n\n"
            f"LIVE WEB RESEARCH:\n{context}\n\n"
            "Return JSON with EXACTLY these keys:\n"
            '- "evidence_quality": string (strong|moderate|thin) with one-sentence justification\n'
            '- "manufacturer_facts": array of objects '
            '{"claim": str, "source_url": str, "manufacturer_or_doc": str}\n'
            '- "practitioner_recommendations": array of objects '
            '{"claim": str, "source_url": str, "note": str}\n'
            '- "dye_sub_printers": array of objects with keys: '
            "model, manufacturer, print_sizes, rated_speed, media_capacity, "
            "supply_cost_notes, source_urls (array). Use null or "
            '"not found in provided sources" for unknown fields.\n'
            '- "cost_per_print_and_margin_examples": array of objects '
            '{"example": str, "assumptions": str, "source_urls": array, '
            '"confidence": "source-backed"|"inferred-from-sources"|"not found"}\n'
            '- "workflow_laptop_tether_queue_delivery": array of strings\n'
            '- "power_backup_transport_tablespace": array of strings\n'
            '- "ordering_payment_file_naming_pickup": array of strings\n'
            '- "keepsakes_during_event_vs_post_event": object with keys '
            "during_event_realistic (array), post_event_or_specialty (array), "
            "not_supported_by_sources (array)\n"
            '- "still_open_questions": array of strings\n'
            '- "source_urls_used": array of strings\n'
            "Do not invent figures. Do not use emojis."
        ),
        max_completion_tokens=4500,
    )
    elapsed = round(time.time() - t0, 2)
    add_call(
        ledger,
        "OpenAI-compatible (AI_INTEGRATIONS)",
        "Synthesize on-site printing research addendum (no manuscript)",
        OPENAI_SYNTHESIS_EST_USD,
        {
            "model": MODEL,
            "max_completion_tokens": 4500,
            "elapsed_sec": elapsed,
            "estimate_basis": "conservative flat estimate for denser printing synthesis",
        },
    )

    # Merge into prior brief payload
    prior_brief = prior.get("research_brief") if isinstance(prior.get("research_brief"), dict) else {}
    merged = dict(prior)
    merged["stage"] = "research_plus_printing"
    merged["status"] = "AWAITING_HUMAN_REVIEW"
    merged["printing_research"] = printing_brief
    merged["printing_raw_searches"] = raw_searches
    merged["ledger"] = ledger
    merged["updated_at"] = datetime.now(timezone.utc).isoformat()
    merged["next_checkpoint"] = (
        "Approve updated research (including printing evidence) before title options"
    )
    merged["blocked_until_approval"] = [
        "title options",
        "outline",
        "manuscript",
        "visuals",
        "cover/image spend",
        "preflight",
        "save/export",
    ]

    # Update prior open questions / summary honesty
    if isinstance(prior_brief, dict):
        prior_brief = dict(prior_brief)
        prior_brief["printing_addendum_attached"] = True
        prior_brief["printing_evidence_quality"] = printing_brief.get("evidence_quality")
        merged["research_brief"] = prior_brief

    (OUT / "paid_call_ledger.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    (OUT / "research_brief.json").write_text(json.dumps(merged, indent=2), encoding="utf-8")
    (OUT / "printing_research.json").write_text(
        json.dumps(
            {
                "printing_research": printing_brief,
                "raw_searches": raw_searches,
                "ledger_snapshot": ledger["totals"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Markdown addendum
    lines: list[str] = [
        f"# On-Site Printing Research Addendum — {TOPIC}",
        f"Author (listed only): {AUTHOR}",
        "",
        f"## Evidence quality",
        str(printing_brief.get("evidence_quality") or ""),
        "",
        "## Manufacturer-supported facts",
    ]
    for item in printing_brief.get("manufacturer_facts") or []:
        if isinstance(item, dict):
            lines.append(
                f"- {item.get('claim')} "
                f"(doc: {item.get('manufacturer_or_doc')}; {item.get('source_url')})"
            )
        else:
            lines.append(f"- {item}")

    lines += ["", "## Practitioner recommendations (not manufacturer specs)"]
    for item in printing_brief.get("practitioner_recommendations") or []:
        if isinstance(item, dict):
            lines.append(
                f"- {item.get('claim')} ({item.get('source_url')}) "
                f"— {item.get('note')}"
            )
        else:
            lines.append(f"- {item}")

    lines += ["", "## Dye-sub printers found in sources"]
    for p in printing_brief.get("dye_sub_printers") or []:
        if not isinstance(p, dict):
            lines.append(f"- {p}")
            continue
        lines.append(f"### {p.get('manufacturer')} {p.get('model')}")
        for k in (
            "print_sizes",
            "rated_speed",
            "media_capacity",
            "supply_cost_notes",
        ):
            lines.append(f"- {k}: {p.get(k)}")
        urls = p.get("source_urls") or []
        if urls:
            lines.append(f"- sources: {', '.join(urls)}")

    lines += ["", "## Cost per print / margin examples"]
    for ex in printing_brief.get("cost_per_print_and_margin_examples") or []:
        if isinstance(ex, dict):
            lines.append(
                f"- [{ex.get('confidence')}] {ex.get('example')} "
                f"(assumptions: {ex.get('assumptions')}; "
                f"sources: {', '.join(ex.get('source_urls') or [])})"
            )
        else:
            lines.append(f"- {ex}")

    lines += ["", "## Workflow: laptop / tether / queue / delivery"]
    for x in printing_brief.get("workflow_laptop_tether_queue_delivery") or []:
        lines.append(f"- {x}")
    lines += ["", "## Power / backup / transport / table space"]
    for x in printing_brief.get("power_backup_transport_tablespace") or []:
        lines.append(f"- {x}")
    lines += ["", "## Ordering / payment / file naming / pickup"]
    for x in printing_brief.get("ordering_payment_file_naming_pickup") or []:
        lines.append(f"- {x}")

    keeps = printing_brief.get("keepsakes_during_event_vs_post_event") or {}
    if isinstance(keeps, dict):
        lines += ["", "## Keepsakes — during event (source-supported as realistic)"]
        for x in keeps.get("during_event_realistic") or []:
            lines.append(f"- {x}")
        lines += ["", "## Keepsakes — post-event / specialty"]
        for x in keeps.get("post_event_or_specialty") or []:
            lines.append(f"- {x}")
        lines += ["", "## Keepsakes — not supported by sources"]
        for x in keeps.get("not_supported_by_sources") or []:
            lines.append(f"- {x}")

    lines += ["", "## Still open questions"]
    for x in printing_brief.get("still_open_questions") or []:
        lines.append(f"- {x}")
    lines += ["", "## Sources used"]
    for u in printing_brief.get("source_urls_used") or []:
        lines.append(f"- {u}")
    lines += [
        "",
        "## Paid-call ledger (estimate)",
        f"Total estimated USD so far: {ledger['totals']['estimated_usd']}",
        f"Remaining under ${BUDGET_CAP:.2f} cap: {round(BUDGET_CAP - ledger['totals']['estimated_usd'], 4)}",
    ]
    for c in ledger["calls"]:
        lines.append(
            f"- {c['provider']}: {c['purpose']} — est ${c['estimated_cost_usd']:.4f}"
        )

    (OUT / "printing_research.md").write_text("\n".join(lines), encoding="utf-8")

    # Refresh combined research_brief.md with pointer to addendum
    base_md = OUT / "research_brief.md"
    header = (
        f"# Research Brief (updated) — {TOPIC}\n"
        f"Author (listed only): {AUTHOR}\n\n"
        "## Status\n"
        "Base research + **on-site printing addendum** attached. "
        "Awaiting human review before title options.\n\n"
        f"See also: `printing_research.md`\n\n"
        f"Printing evidence quality: {printing_brief.get('evidence_quality')}\n\n"
        "---\n\n"
    )
    if base_md.is_file():
        old = base_md.read_text(encoding="utf-8")
        # Strip old header if re-run
        if old.startswith("# Research Brief"):
            # keep body after first title block by appending addendum note at top
            pass
        base_md.write_text(header + old + "\n\n---\n\n" + "\n".join(lines), encoding="utf-8")
    else:
        base_md.write_text(header + "\n".join(lines), encoding="utf-8")

    print("OK")
    print("EST_TOTAL", ledger["totals"]["estimated_usd"])
    print("CALLS", ledger["totals"]["paid_calls"])
    print("EVIDENCE", printing_brief.get("evidence_quality"))


if __name__ == "__main__":
    main()
