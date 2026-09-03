"""Ebook workspace topic research engine.

Runs the paid research step for an Ebook Project workspace: one Tavily web
search on the book topic plus one OpenAI synthesis call that turns the search
results into the workspace research payload (summary, key findings, notes
sections, source URLs).

FACTORY_TEST_MODE never calls a provider: a deterministic offline payload is
returned so the release gate spends $0. Live provider failures fail open to an
input-backed draft (marked as such) rather than crashing the workspace.
"""
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

RESEARCH_UNIT_USD = 0.50
RESEARCH_FAILED_MESSAGE = (
    "Research could not produce usable findings. Nothing was saved — "
    "request a new estimate and try again."
)
_MAX_FINDINGS = 12
_MAX_SOURCES = 12


def _test_mode() -> bool:
    return str(os.environ.get("FACTORY_TEST_MODE") or "") == "1"


def _clean_str(value) -> str:
    return str(value or "").strip()


def _clean_list(value, limit: int) -> list[str]:
    out = []
    for item in list(value or []):
        text = _clean_str(item)
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _offline_payload(topic: str, audience: str, outcome: str) -> dict:
    """Deterministic zero-provider payload for tests and offline fallback."""
    topic = _clean_str(topic) or "the book topic"
    audience = _clean_str(audience) or "general readers"
    outcome = _clean_str(outcome) or "a practical result"
    return {
        "summary": (
            f"Research draft for a book about {topic}, written for {audience}, "
            f"whose goal is {outcome}. This draft was assembled from the "
            "workspace inputs without a live web search."
        ),
        "key_findings": [
            f"The book must stay focused on {topic} from the first chapter.",
            f"Every chapter should be written for {audience} in plain language.",
            f"Each chapter should move the reader toward {outcome}.",
            "Claims that need evidence should cite a source or be softened.",
        ],
        "notes_sections": {
            "Audience": f"Primary audience: {audience}.",
            "Goal": f"Reader outcome: {outcome}.",
            "Scope": f"Topic boundary: {topic}. Avoid adjacent topics unless a chapter needs them.",
        },
        "source_urls": [],
        "live_search": False,
        "paid_calls": 0,
    }


def _tavily_topic_search(topic: str, audience: str) -> tuple[bool, str, list[str]]:
    """Return (live_used, context_text, source_urls). Fails open."""
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return False, "", []
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=key)
        query = f"what readers need to know about {topic}" + (
            f" for {audience}" if audience else ""
        )
        search = client.search(
            query=query,
            search_depth="advanced",
            max_results=8,
            include_answer=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ebook research Tavily search failed; continuing without web results: %s", exc)
        return False, "", []
    access_date = datetime.now(timezone.utc).date().isoformat()
    urls: list[str] = []
    chunks: list[str] = []
    answer = _clean_str(search.get("answer"))
    if answer:
        chunks.append(f"Web summary ({access_date}): {answer}")
    for result in list(search.get("results") or [])[:_MAX_SOURCES]:
        url = _clean_str(result.get("url"))
        title = _clean_str(result.get("title")) or "Untitled"
        content = _clean_str(result.get("content"))
        if url:
            urls.append(url)
        if content:
            chunks.append(f"Source: {title} ({url})\n{content}")
    return True, "\n\n".join(chunks), urls


def run_topic_research(*, topic: str, audience: str = "", outcome: str = "") -> dict:
    """Produce the workspace research payload for a book topic.

    Returns a dict with: summary, key_findings, notes_sections, source_urls,
    live_search (bool), paid_calls (int provider requests actually made).
    """
    topic = _clean_str(topic)
    if not topic:
        raise ValueError("The workspace has no topic to research.")
    audience = _clean_str(audience)
    outcome = _clean_str(outcome)

    if _test_mode():
        return _offline_payload(topic, audience, outcome)

    paid_calls = 0
    live_search, context, source_urls = _tavily_topic_search(topic, audience)
    if live_search:
        paid_calls += 1

    system = (
        "You are a book research analyst. Using ONLY the provided web research "
        "and inputs, produce research notes for writing a practical non-fiction "
        "book. Return a JSON object with exactly these keys: "
        '"summary" (3-6 sentence overview of what the book must cover), '
        '"key_findings" (array of 5-10 short factual strings the manuscript '
        "must respect), "
        '"notes_sections" (object mapping short section names to 1-3 sentence '
        "notes, e.g. Audience, Common mistakes, Terminology). "
        "Never invent statistics. If the web research is empty, base the notes "
        "on the inputs alone and say so in the summary."
    )
    user = (
        f"Book topic: {topic}\n"
        f"Audience: {audience or 'general readers'}\n"
        f"Reader outcome: {outcome or 'a practical result'}\n\n"
        f"Web research:\n{context or '(no web results available)'}"
    )
    raw: dict = {}
    try:
        from ai_client import chat_json

        raw = chat_json(system=system, user=user, max_completion_tokens=3000)
        paid_calls += 1
        if not isinstance(raw, dict):
            raw = {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ebook research synthesis call failed; using input-backed draft: %s", exc)
        raw = {}

    if not _clean_str(raw.get("summary")):
        fallback = _offline_payload(topic, audience, outcome)
        fallback["source_urls"] = _clean_list(source_urls, _MAX_SOURCES)
        fallback["live_search"] = bool(live_search)
        fallback["paid_calls"] = paid_calls
        return fallback

    notes = raw.get("notes_sections")
    notes_sections = {}
    if isinstance(notes, dict):
        for name, text in list(notes.items())[:8]:
            name = _clean_str(name)
            text = _clean_str(text)
            if name and text:
                notes_sections[name] = text
    findings = _clean_list(raw.get("key_findings"), _MAX_FINDINGS)
    return {
        "summary": _clean_str(raw.get("summary")),
        "key_findings": findings,
        "notes_sections": notes_sections,
        "source_urls": _clean_list(source_urls, _MAX_SOURCES),
        "live_search": bool(live_search),
        "paid_calls": paid_calls,
    }


TITLE_UNIT_USD = 0.15
OUTLINE_UNIT_USD = 0.20
TITLE_FAILED_MESSAGE = (
    "Title generation could not produce usable options. Nothing was saved — "
    "request a new estimate and try again."
)
OUTLINE_FAILED_MESSAGE = (
    "Outline generation could not produce a usable outline. Nothing was saved — "
    "request a new estimate and try again."
)


def _research_context(research: dict | None) -> str:
    research = research or {}
    findings = "\n".join(f"- {f}" for f in _clean_list(research.get("key_findings"), _MAX_FINDINGS))
    notes = "\n".join(
        f"{name}: {text}" for name, text in dict(research.get("notes_sections") or {}).items()
    )
    return (
        f"Research summary:\n{_clean_str(research.get('summary')) or '(none)'}\n\n"
        f"Key findings:\n{findings or '(none)'}\n\n"
        f"Notes:\n{notes or '(none)'}"
    )


def _offline_title_options(topic: str, audience: str, outcome: str) -> list[dict]:
    topic_t = (_clean_str(topic) or "Your Topic").title()
    audience = _clean_str(audience) or "beginners"
    outcome = _clean_str(outcome) or "real results"
    return [
        {
            "id": "T1",
            "title": f"{topic_t}: A Practical Guide",
            "subtitle": f"Step-by-step help for {audience} who want {outcome}",
        },
        {
            "id": "T2",
            "title": f"Getting Started with {topic_t}",
            "subtitle": f"What {audience} need to know first",
        },
        {
            "id": "T3",
            "title": f"The {topic_t} Handbook",
            "subtitle": f"From first steps to {outcome}",
        },
    ]


def generate_title_options(*, topic: str, audience: str = "", outcome: str = "", research: dict | None = None) -> dict:
    """Produce 3 title/subtitle options. Returns {options, paid_calls}."""
    topic = _clean_str(topic)
    if not topic:
        raise ValueError("The workspace has no topic for title options.")
    if _test_mode():
        return {"options": _offline_title_options(topic, audience, outcome), "paid_calls": 0}
    system = (
        "You are a book-title specialist for practical non-fiction. Return a "
        'JSON object: {"options": [{"id": "T1", "title": "...", "subtitle": "..."}, ...]} '
        "with exactly 3 options (ids T1, T2, T3). Titles must be specific to the "
        "topic, honest (no unverifiable claims), and each subtitle must say who "
        "the book is for or what it delivers."
    )
    user = (
        f"Book topic: {topic}\nAudience: {_clean_str(audience) or 'general readers'}\n"
        f"Reader outcome: {_clean_str(outcome) or 'a practical result'}\n\n"
        + _research_context(research)
    )
    paid_calls = 0
    raw: dict = {}
    try:
        from ai_client import chat_json

        raw = chat_json(system=system, user=user, max_completion_tokens=1200)
        paid_calls += 1
        if not isinstance(raw, dict):
            raw = {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Title options call failed; using input-backed options: %s", exc)
        raw = {}
    options = []
    for i, opt in enumerate(list(raw.get("options") or [])[:3]):
        if not isinstance(opt, dict):
            continue
        title = _clean_str(opt.get("title"))
        if not title:
            continue
        options.append(
            {
                "id": _clean_str(opt.get("id")) or f"T{i + 1}",
                "title": title,
                "subtitle": _clean_str(opt.get("subtitle")),
            }
        )
    if len(options) < 2:
        options = _offline_title_options(topic, audience, outcome)
    return {"options": options, "paid_calls": paid_calls}


def _offline_outline_option(topic: str, audience: str, outcome: str) -> dict:
    topic = _clean_str(topic) or "the topic"
    audience = _clean_str(audience) or "beginners"
    outcome = _clean_str(outcome) or "a practical result"
    names = [
        f"Why {topic} Matters to You",
        "What You Need Before You Start",
        "The Fundamentals, Explained Simply",
        "Your First Practical Steps",
        "Common Mistakes and How to Avoid Them",
        "Tools, Costs, and Planning",
        "Putting It All Together",
        f"Your 30-Day Plan Toward {outcome}",
    ]
    chapters = [
        {
            "n": i + 1,
            "title": name,
            "bullets": [f"Cover this step for {audience}: {name}."],
        }
        for i, name in enumerate(names)
    ]
    return {
        "id": "O1",
        "name": "Practical journey outline",
        "estimated_chapters": len(chapters),
        "chapters": chapters,
    }


def generate_outline_options(
    *,
    topic: str,
    audience: str = "",
    outcome: str = "",
    title: str = "",
    subtitle: str = "",
    research: dict | None = None,
) -> dict:
    """Produce 1-2 chapter outline options. Returns {options, paid_calls}."""
    topic = _clean_str(topic)
    if not topic:
        raise ValueError("The workspace has no topic for an outline.")
    if _test_mode():
        return {"options": [_offline_outline_option(topic, audience, outcome)], "paid_calls": 0}
    system = (
        "You are a book-outline architect for practical non-fiction. Return a "
        'JSON object: {"options": [{"id": "O1", "name": "...", "chapters": '
        '[{"n": 1, "title": "...", "bullets": ["purpose sentence", ...]}, ...]}]} '
        "with 1 or 2 options. Each option needs 6-10 chapters in reader-journey "
        "order; every chapter needs 1-3 purpose bullets grounded in the research."
    )
    user = (
        f"Book topic: {topic}\nApproved title: {_clean_str(title)} — {_clean_str(subtitle)}\n"
        f"Audience: {_clean_str(audience) or 'general readers'}\n"
        f"Reader outcome: {_clean_str(outcome) or 'a practical result'}\n\n"
        + _research_context(research)
    )
    paid_calls = 0
    raw: dict = {}
    try:
        from ai_client import chat_json

        raw = chat_json(system=system, user=user, max_completion_tokens=3000)
        paid_calls += 1
        if not isinstance(raw, dict):
            raw = {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Outline options call failed; using input-backed outline: %s", exc)
        raw = {}
    options = []
    for i, opt in enumerate(list(raw.get("options") or [])[:2]):
        if not isinstance(opt, dict):
            continue
        chapters = []
        for j, ch in enumerate(list(opt.get("chapters") or [])[:12]):
            if not isinstance(ch, dict):
                continue
            ch_title = _clean_str(ch.get("title"))
            if not ch_title:
                continue
            bullets = _clean_list(ch.get("bullets"), 3) or [f"Cover: {ch_title}."]
            chapters.append({"n": j + 1, "title": ch_title, "bullets": bullets})
        if len(chapters) >= 6:
            options.append(
                {
                    "id": _clean_str(opt.get("id")) or f"O{i + 1}",
                    "name": _clean_str(opt.get("name")) or f"Outline option {i + 1}",
                    "estimated_chapters": len(chapters),
                    "chapters": chapters,
                }
            )
    if not options:
        options = [_offline_outline_option(topic, audience, outcome)]
    return {"options": options, "paid_calls": paid_calls}
